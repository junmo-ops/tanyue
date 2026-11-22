import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import Switch from 'antd-mobile/es/components/switch'
import { requestJson, postJson } from '../api/client.js'
import { siteId, siteUrl } from '../api/site.js'
import { prefersDark, themeStorageKey } from '../appearance.js'
import useViewportInsets from '../useViewportInsets.js'
import Feed from './Feed.jsx'
import Sites from './Sites.jsx'
import { Body, Notice, Sheet } from './ui.jsx'
import './mobile.css'

const Admin=lazy(()=>import('./Admin.jsx'))
const Rankings=lazy(()=>import('./Rankings.jsx'))
const Words=lazy(()=>import('./Words.jsx'))
const Insights=lazy(()=>import('./Insights.jsx'))
const Detail=lazy(()=>import('./Detail.jsx'))
const here=()=>window.location.pathname+window.location.search
const menuItems=[['排行榜','/rankings'],['数据分析','/insights'],['随机发现','/words'],['采集管理','/admin']]

export default function MobileApp(){
  useViewportInsets()
  const [location,setLocation]=useState(here)
  const [sites,setSites]=useState(null)
  const [forums,setForums]=useState([])
  const [revision,retry]=useState(0)
  const [error,setError]=useState('')
  const [dark,setDark]=useState(prefersDark)
  const [sheet,setSheet]=useState('')
  const [seen,setSeen]=useState({})
  const [status,setStatus]=useState(null)
  const savedScroll=useRef(null)
  const pathname=location.split('?')[0]
  const feedActive=pathname==='/'
  useLayoutEffect(()=>{
    const root=document.documentElement
    const meta=document.querySelector('meta[name="theme-color"]')
    const previous=meta?.content
    root.dataset.tyMobile='';root.dataset.theme=dark?'dark':'light'
    if(meta)meta.content=dark?'#18282f':'#ffffff'
    try{localStorage.setItem(themeStorageKey,root.dataset.theme)}catch{/* Storage may be disabled. */}
    return ()=>{delete root.dataset.tyMobile;if(meta)meta.content=previous}
  },[dark])
  useEffect(()=>{
    const ctrl=new AbortController()
    requestJson('/api/sites',{signal:ctrl.signal}).then(({items})=>{
      if(ctrl.signal.aborted)return
      if(items.length && siteId==='default'&&!items.some(s=>s.id===siteId)){window.location.replace(siteUrl(here(),items[0].id));return}
      setSites(items)
    }).catch(e=>{if(!ctrl.signal.aborted)setError(e.message)})
    return ()=>ctrl.abort()
  },[revision])
  useEffect(()=>{
    if(!sites?.length)return
    const ctrl=new AbortController()
    requestJson('/api/forums',{signal:ctrl.signal}).then(r=>{if(!ctrl.signal.aborted)setForums(r.items)}).catch(()=>{})
    return ()=>ctrl.abort()
  },[sites])
  useEffect(()=>{
    if(sheet!=='menu')return
    const ctrl=new AbortController()
    requestJson('/api/status',{signal:ctrl.signal}).then(r=>{if(!ctrl.signal.aborted)setStatus(r)}).catch(()=>{})
    return ()=>ctrl.abort()
  },[sheet])
  useEffect(()=>{
    function pop(){savedScroll.current=window.history.state?.tyScroll??0;setSheet('');setLocation(here())}
    window.addEventListener('popstate',pop)
    return ()=>window.removeEventListener('popstate',pop)
  },[])
  useLayoutEffect(()=>{
    if(savedScroll.current!==null){window.scrollTo(0,savedScroll.current);savedScroll.current=null}
  },[location])
  const go=useCallback((url,options={})=>{
    const path=siteUrl(url)
    const state=window.history.state||{}
    const current=here()
    if(current!==path){
      if(!options.replace)window.history.replaceState({...state,tyScroll:window.scrollY},'',current)
      window.history[options.replace?'replaceState':'pushState']({...state,tyFrom:options.replace?state.tyFrom:current,tyScroll:0},'',path)
      savedScroll.current=0
    }
    setSheet('');setLocation(here())
  },[])
  const back=useCallback(()=>{if(window.history.state?.tyFrom)window.history.back();else go('/',{replace:true})},[go])
  const onSeen=useCallback(async tid=>{
    try{await postJson('/api/seen',{tid,seen:1});setSeen(prev=>({...prev,[tid]:true}));return true}
    catch{return false}
  },[])
  const shared={go,back,location,forums,seen,onSeen}
  let page=null
  if(pathname.startsWith('/thread/'))page=<Detail key={pathname} {...shared} tid={decodeURIComponent(pathname.slice(8))}/>
  else if(pathname==='/admin')page=<Admin {...shared}/>
  else if(pathname==='/rankings')page=<Rankings {...shared}/>
  else if(pathname==='/words')page=<Words {...shared}/>
  else if(pathname==='/insights')page=<Insights {...shared}/>
  const siteName=sites?.find(s=>s.id===siteId)?.name||'选择论坛'
  return <main className="ty-mobile">{!sites?<Body><Notice>{error||'正在读取站点…'}</Notice>{error && <button onClick={()=>{setError('');retry(n=>n+1)}}>重新加载</button>}</Body>:
    !sites.length?<Sites first/>:<>
      <div hidden={!feedActive}><Feed {...shared} sites={sites} siteName={siteName} active={feedActive} openSites={()=>setSheet('sites')} openMenu={()=>setSheet('menu')}/></div>
      <Suspense fallback={<Body><Notice>正在载入页面…</Notice></Body>}>{page}</Suspense>
      {!feedActive&&!page&&<Body><Notice>页面不存在</Notice><button onClick={back}>返回</button></Body>}
      {sheet==='menu'&&<Sheet title="更多功能" onClose={()=>setSheet('')}>{menuItems.map(([label,url])=><button key={url} className="ty-menu-line" onClick={()=>go(url)}><span>{label}</span><span>›</span></button>)}
        <div className="ty-menu-line"><span>深色模式</span><Switch aria-label="深色模式" checked={dark} onChange={setDark}/></div>
        {status && <Notice>已收录 {Number(status.thread_count||0).toLocaleString()} 篇{status.last_sync?.finished_at && ' · '+status.last_sync.finished_at}</Notice>}</Sheet>}
      {sheet==='sites'&&<Sheet title="切换论坛" onClose={()=>setSheet('')}>{sites.map(s=><button key={s.id} className="ty-menu-line" onClick={()=>s.id===siteId?setSheet(''):window.location.assign(siteUrl('/',s.id))}><span>{s.name}</span><span>{s.id===siteId?'✓':''}</span></button>)}<button className="ty-menu-line" onClick={()=>setSheet('add')}>接入其他论坛 <span>＋</span></button></Sheet>}
      {sheet==='add'&&<Sites onClose={()=>setSheet('')}/>}
    </>}</main>
}
