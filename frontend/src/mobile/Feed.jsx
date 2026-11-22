import { useEffect, useRef, useState } from 'react'
import { LoadingContent } from '../Loading.jsx'
import Input from 'antd-mobile/es/components/input'
import Choice from './Choice.jsx'
import dayjs from 'dayjs'
import { SearchOutline, MoreOutline, DownOutline, CheckOutline, HeartOutline, MinusOutline, RightOutline } from 'antd-mobile-icons'
import Switch from 'antd-mobile/es/components/switch'
import { postJson } from '../api/client.js'
import { siteId, siteUrl } from '../api/site.js'
import useThreads from '../features/threads/useThreads.js'
import { DEFAULT_FILTERS, HOT_DAY_VALUES, MAX_HOT_PERIOD, hotPeriodRange, parseUrlState, persistThreadFilters } from '../features/threads/filters.js'
import { ORDER_OPTIONS, SORT_OPTIONS, RECOMMEND_PERCENT_OPTIONS, PAGE_SIZE_OPTIONS } from '../shared.jsx'
import { Body, Chip, Field, KV, Notice, Primary, Sheet, Tabs, Tools, Chevron, Disclosure } from './ui.jsx'
import './Feed.css'

const modes = [['hot','近期热帖'],['recommend','随机推荐'],['all','全部帖子']]
function listUrl(filters,page) {
  const query=new URLSearchParams({view:filters.view_mode,page:String(page)})
  for(const [key,value] of Object.entries(filters)) {
    if(key==='dateRange') {
      for(const [index,param] of ['posted_date_from','posted_date_to'].entries()) {
        if(value?.[index]) query.set(param,value[index].format('YYYY-MM-DD'))
      }
    } else if(key!=='view_mode' && value!==DEFAULT_FILTERS[key] && value!=null && value!==''){
      query.set(key,typeof value==='boolean'?Number(value):value)
    }
  }
  return '/?'+query
}
const choices = items => items.map(({value,label}) => [value,label])

export default function Feed({go,forums,siteName,openSites,openMenu,active,location,seen,onSeen}) {
  const [{filters,page},setRoute]=useState(parseUrlState)
  const {data,setData,loading,loadError,loadThreads}=useThreads()
  const last=useRef(null)
  const [panel,setPanel]=useState('')
  const [draft,setDraft]=useState(filters)
  const [thread,setThread]=useState(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [undo,setUndo]=useState(null)
  useEffect(()=>{
    if(!active || last.current===location)return
    last.current=null
    const next=parseUrlState()
    const storage='forum-browser.thread-filters.v1'+(siteId==='default'?'':'.'+siteId)
    try{
      if(!window.localStorage.getItem(storage)&&!new URLSearchParams(window.location.search).has('view')&&next.filters.view_mode==='hot'){
        next.filters={...next.filters,hide_seen:true,hot_days:7}
      }
    }catch{/* Filters remain available without persistent storage. */}
    setRoute(next);setPanel('');setUndo(null)
    let current=true
    loadThreads(next.filters,next.page).then(ok=>{if(current&&ok)last.current=location})
    return ()=>{current=false}
  },[active,location,loadThreads])
  const apply=(patch,nextPage=1)=>{
    const next={...filters,...patch}
    persistThreadFilters(next);setPanel('');go(listUrl(next,nextPage))
  }
  const open=name=>{setDraft({...filters});setPanel(name)}
  const update=(key,value)=>setDraft(current=>({...current,[key]:value}))
  const close=()=>{if(!busy)setPanel('')}
  const forum=id=>forums.find(item=>String(item.fid)===String(id))?.forum_name||('fid '+id)
  function markRead(item){
    if(!seen[item.tid]&&!Number(item.seen))onSeen(item.tid).then(saved=>{if(!saved)setError('已看状态保存失败，请重新打开帖子再试。')})
  }
  function openComments(item){
    setPanel('')
    go('/thread/'+encodeURIComponent(item.tid))
    markRead(item)
  }
  async function saveAction(kind){
    if(busy||!thread)return
    setBusy(true);setError('')
    try{
      const fetchSwitch=kind==='fetch'
      const next=thread.feedback===kind?'':kind
      const result=fetchSwitch?await postJson('/api/comment-fetch',{tid:thread.tid,fetch_comments:Number(thread.fetch_comments)?0:1}):await postJson('/api/feedback',{tid:thread.tid,feedback:next})
      setData(current=>({...current,items:current.items.map(item=>item.tid===thread.tid?{...item,...(fetchSwitch?{fetch_comments:result.fetch_comments}:{feedback:result.feedback})}:item)}))
      if(!fetchSwitch&&next==='dislike'&&!filters.show_disliked)setUndo(thread)
      setPanel('')
    }catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function restore(){
    if(!undo||busy)return
    setBusy(true)
    try{await postJson('/api/feedback',{tid:undo.tid,feedback:undo.feedback||''});setData(current=>({...current,items:current.items.map(i=>i.tid===undo.tid?undo:i)}));setUndo(null)}catch(e){setError(e.message)}finally{setBusy(false)}
  }
  const visible=data.items.filter(t=>(!filters.hide_seen||!(Number(t.seen)||seen[t.tid]))&&(filters.show_disliked||t.feedback!=='dislike')&&(!filters.only_liked||t.feedback==='like'))
  const pages=Math.max(1,Math.ceil(data.total/(data.page_size||filters.page_size)))
  const range=hotPeriodRange(draft)
  return <>
    <div className="ty-feed-toolbar">
      <header className="ty-bar ty-feed-bar"><b className="ty-brand">坛</b><button className="ty-site-selector" onClick={openSites}>{siteName} <DownOutline/></button><button aria-label="搜索帖子" onClick={()=>open('search')}><SearchOutline/></button><button aria-label="更多功能" onClick={openMenu}><MoreOutline/></button></header>
      <Tabs items={modes} value={filters.view_mode} onChange={value=>apply({view_mode:value})}/>
      <Tools>{filters.view_mode==='hot'&&<Chip onClick={()=>open('period')}>{filters.hot_period?'每期':'近'} {filters.hot_days} 天 <Chevron/></Chip>}
        <Chip className="ty-seen-toggle" active={filters.hide_seen} onClick={()=>apply({hide_seen:!filters.hide_seen})}>
          <span className="ty-seen-check" aria-hidden="true">{filters.hide_seen&&<CheckOutline className="ty-icon" aria-hidden="true"/>}</span>隐藏已看
        </Chip>
        <Chip onClick={()=>open('filters')}>筛选</Chip>{filters.view_mode==='recommend'&&<Chip disabled={loading} onClick={()=>loadThreads(filters,page,{refresh:true})}>换一批</Chip>}
        {filters.q&&<Chip onClick={()=>open('search')}>{filters.q}</Chip>}{filters.fid&&<Chip onClick={()=>open('filters')}>{forum(filters.fid)}</Chip>}
      </Tools>
    </div>
    <Body>{(error||loadError)&&<Notice>{error||loadError} <button onClick={()=>{setError('');loadThreads(filters,page)}}>重试</button></Notice>}
      {undo&&<Notice>已收起不感兴趣的帖子 <button disabled={busy} onClick={restore}>撤销</button></Notice>}
      {loading&&!data.items.length&&<LoadingContent/>}
      {visible.map(item=>{
        const isSeen=seen[item.tid]||Number(item.seen)
        const boardName=forum(item.fid)
        const postedDate=item.posted_at?.slice(0,10)
        return <article className={'ty-feed-row'+(isSeen?' is-seen':'')} key={item.tid}>
          <a href={item.official_url || siteUrl('/thread/'+encodeURIComponent(item.tid))}
            target={item.official_url ? '_blank' : undefined} rel="noreferrer"
            onClick={()=>markRead(item)}><strong>{item.title}</strong></a>
          <div className="ty-meta">
            <div className="ty-feed-post-meta">
              <span className="ty-feed-board" title={boardName}>{boardName}</span>
              {postedDate&&<time dateTime={postedDate}>{postedDate}</time>}
              {isSeen? <span className="ty-feed-seen">· 已看</span> : null}
            </div>
            <span className="ty-feed-replies">{Number(item.reply_count||0).toLocaleString()} 回复</span>
            <button type="button" className="ty-feed-actions" aria-label={'帖子操作：'+item.title}
              aria-haspopup="dialog" onClick={()=>{setThread(item);setPanel('actions')}}>
              <MoreOutline aria-hidden="true"/>
            </button>
          </div>
        </article>
      })}
      {!loading&&!loadError&&!visible.length&&<Notice>当前条件下没有帖子 <button onClick={()=>apply({...DEFAULT_FILTERS,view_mode:filters.view_mode})}>重置筛选</button></Notice>}
      {filters.view_mode!=='recommend'&&pages>1&&<nav className="ty-read-pages"><button disabled={page<=1} onClick={()=>apply({},page-1)}>上一页</button><span>{page} / {pages}</span><button disabled={page>=pages} onClick={()=>apply({},page+1)}>下一页</button></nav>}
    </Body>
    {panel==='search'&&<Sheet title="搜索帖子" onClose={close} footer={<Primary onClick={()=>apply({q:draft.q.trim()})}>搜索</Primary>}><Field label="标题关键词或 TID"><Input type="search" value={draft.q} onChange={v=>update('q',v)} onEnterPress={()=>apply({q:draft.q.trim()})} /></Field></Sheet>}
    {panel==='period'&&<Sheet title="热帖时间范围" onClose={close} footer={<Primary disabled={!Number.isInteger(+draft.hot_days)||draft.hot_days<1||draft.hot_days>365} onClick={()=>apply({hot_days:+draft.hot_days,hot_period:draft.hot_period,hot_anchor:draft.hot_period?range.anchor:''})}>应用</Primary>}>
      <Tools>{HOT_DAY_VALUES.map(n=><Chip key={n} active={+draft.hot_days===n} onClick={()=>update('hot_days',n)}>{n} 天</Chip>)}</Tools>
      <Field label="自定义天数"><Input type="number" min={1} max={365} value={String(draft.hot_days)} onChange={v=>update('hot_days',v)}/></Field>
      <div className="ty-read-pages"><button disabled={draft.hot_period>=MAX_HOT_PERIOD} onClick={()=>update('hot_period',draft.hot_period+1)}>上一期</button><span>{range.from.slice(5)} — {range.to.slice(5)}</span><button disabled={!draft.hot_period} onClick={()=>update('hot_period',draft.hot_period-1)}>下一期</button></div></Sheet>}
    {panel==='filters'&&<Sheet title="筛选帖子" onClose={close} footer={<><button onClick={close}>取消</button><Primary onClick={()=>apply(draft)}>应用筛选</Primary></>}>
      <Choice inline label="板块" value={draft.fid} options={[['','全部板块'],...forums.map(f=>[f.fid,f.forum_name])]} onChange={v=>update('fid',v)}/>
      <Field label="排除关键词"><Input placeholder="输入关键词" value={draft.exclude_q} onChange={v=>update('exclude_q',v)} /></Field>
      {draft.author_id&&<KV label="作者">{draft.author_name||draft.author_id} <button onClick={()=>setDraft({...draft,author_id:'',author_name:''})}>清除</button></KV>}
      {draft.view_mode==='all'&&<><Choice label="排序" value={draft.sort} options={choices(SORT_OPTIONS)} onChange={v=>update('sort',v)}/><Choice label="顺序" value={draft.order} options={choices(ORDER_OPTIONS)} onChange={v=>update('order',v)}/>
        {['开始日期','结束日期'].map((label,i)=><Field key={label} label={label}><Input type="date" value={draft.dateRange?.[i]?.format('YYYY-MM-DD')||''} onChange={v=>{const dates=[...(draft.dateRange||[null,null])];dates[i]=v?dayjs(v):null;update('dateRange',dates)}}/></Field>)}</>}
      {draft.view_mode==='recommend'?<Choice label="推荐范围" value={draft.recommend_top_percent} options={choices(RECOMMEND_PERCENT_OPTIONS)} onChange={v=>update('recommend_top_percent',+v)}/>:<Choice inline label="每页帖子" value={draft.page_size} options={PAGE_SIZE_OPTIONS.map(({value})=>[value,value+' 篇'])} onChange={v=>update('page_size',+v)}/>}
      <Disclosure className="ty-filter-extra" label="更多筛选">{Object.entries({show_disliked:'显示不感兴趣',only_liked:'只看感兴趣'}).map(([key,label])=><KV key={key} label={label}><Switch aria-label={label} checked={draft[key]} onChange={v=>update(key,v)}/></KV>)}<button className="ty-link" onClick={()=>setDraft({...DEFAULT_FILTERS,view_mode:filters.view_mode,hide_seen:filters.hide_seen})}>重置筛选</button></Disclosure>
    </Sheet>}
    {panel==='actions'&&thread&&<Sheet title="帖子操作" onClose={close}><Notice>{thread.title}</Notice><button className="ty-menu-line" onClick={()=>openComments(thread)}>查看本地评论 <RightOutline className="ty-icon" aria-hidden="true"/></button>
      {[['like','感兴趣'],['dislike','不感兴趣'],['fetch','抓取评论']].map(([k,label])=><button key={k} className="ty-menu-line" disabled={busy} aria-pressed={k==='fetch'?!!Number(thread.fetch_comments):thread.feedback===k} onClick={()=>saveAction(k)}>{label}<span>{(k==='fetch'?Number(thread.fetch_comments):thread.feedback===k)?<CheckOutline className="ty-icon" aria-hidden="true"/>:{like:<HeartOutline className="ty-icon" aria-hidden="true"/>,dislike:<MinusOutline className="ty-icon" aria-hidden="true"/>,fetch:<RightOutline className="ty-icon" aria-hidden="true"/>}[k]}</span></button>)}
      {error&&<Notice>{error}</Notice>}</Sheet>}
  </>
}
