import { AddOutline, CheckOutline } from 'antd-mobile-icons'
import Checkbox from 'antd-mobile/es/components/checkbox'
import { useRef, useState } from 'react'
import Input from 'antd-mobile/es/components/input'
import Choice from './Choice.jsx'
import { postJson } from '../api/client.js'
import { siteUrl } from '../api/site.js'
import { Bar, Body, Field, Notice, Primary, Sheet, Disclosure } from './ui.jsx'

export default function Sites({ first, onClose }) {
  const [url,setUrl]=useState('')
  const [cookie,setCookie]=useState('')
  const [name,setName]=useState('')
  const [forums,setForums]=useState(null)
  const [selected,setSelected]=useState([])
  const [sample,setSample]=useState('')
  const [preview,setPreview]=useState(null)
  const [busy,setBusy]=useState('')
  const [error,setError]=useState('')
  const pending=useRef(false)
  function reset(){setForums(null);setPreview(null);setSelected([]);setError('')}
  async function submit(operation){
    if(pending.current)return
    pending.current=true;setBusy(operation);setError('')
    try{
      if(operation==='discover'){
        const data=await postJson('/api/sites/discover',{url:url.trim(),cookie})
        const ids=Object.keys(data.forums||{})
        if(!ids.length)throw Error('未识别到板块，请检查论坛地址和登录权限。')
        setForums(data.forums);setSelected([ids[0]]);setSample(ids[0])
        if(!name.trim())setName(new URL(url.trim()).hostname)
      }else if(operation==='probe'){
        setPreview(await postJson('/api/sites/probe',{url:url.trim(),cookie,fid:sample}))
      }else{
        const result=await postJson('/api/sites',{url:url.trim(),cookie,name:name.trim(),forums:Object.fromEntries(selected.map(id=>[id,forums[id]]))})
        window.location.assign(siteUrl(first?'/admin':'/',result.id))
      }
    }catch(e){setError(e.message)}finally{pending.current=false;setBusy('')}
  }
  const fields=<><Field label="论坛安装地址"><Input type="url" placeholder="https://example.com/bbs/" value={url} onChange={v=>{setUrl(v);reset()}} /></Field>
    <Field label="登录 Cookie · 选填"><Input type="password" autoComplete="off" placeholder="填写登录信息" value={cookie} onChange={v=>{setCookie(v);reset()}} /></Field>
    {error && !forums && <Notice>{error}</Notice>}
    <Primary disabled={!url.trim()||!!busy} onClick={()=>submit('discover')}>{busy==='discover'?'正在识别…':'识别板块'}</Primary></>
  return <>{first?<><Bar title="坛阅"/><Body className="ty-onboard"><h2>接入第一个论坛</h2><p>选择要阅读的 Discuz! 论坛，再挑选要同步的板块。</p>{fields}</Body></>:
    !forums && <Sheet title="接入 Discuz! 论坛" onClose={()=>{if(!busy)onClose()}}>{fields}</Sheet>}
    {forums && <Sheet title="选择采集板块" onClose={()=>{if(!busy)reset()}} footer={<><button disabled={!!busy} onClick={reset}>返回</button><Primary disabled={!name.trim()||!selected.length||!!busy} onClick={()=>submit('save')}>接入论坛</Primary></>}>
      <Field label="站点名称"><Input value={name} maxLength={80} onChange={setName} /></Field>
      {Object.entries(forums).map(([id,label])=><Checkbox block className="ty-check" key={id} checked={selected.includes(id)}
        icon={checked=>checked?<CheckOutline className="ty-icon" aria-hidden="true"/>:<AddOutline className="ty-icon" aria-hidden="true"/>}
        onChange={checked=>setSelected(items=>checked?[...items,id]:items.filter(x=>x!==id))}>{label}</Checkbox>)}
      <Disclosure className="ty-filter-extra" label="取样检查"><Choice label="取样板块" value={sample} options={Object.entries(forums)} onChange={v=>{setSample(v);setPreview(null)}}/>
      <button className="ty-link" disabled={!!busy} onClick={()=>submit('probe')}>预览识别结果</button>
      {preview && <Notice>{preview.title} · 已识别 {preview.count} 条帖子，{preview.comments} 条回复</Notice>}</Disclosure>
      {error && <Notice>{error}</Notice>}
    </Sheet>}</>
}
