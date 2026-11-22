import { LinkOutline } from 'antd-mobile-icons'
import { useEffect, useState } from 'react'
import { LoadingContent } from '../Loading.jsx'
import Input from 'antd-mobile/es/components/input'
import Choice from './Choice.jsx'
import { requestJson } from '../api/client.js'
import useCommentTask from '../features/threads/useCommentTask.js'
import { splitKeywords, COMMENT_PAGE_SIZE_OPTIONS } from '../shared.jsx'
import { Bar, Body, Section, KV, Sheet, Field, Primary, Notice } from './ui.jsx'
import './Feed.css'

const defaults={q:'',exclude_q:'',page_size:50}
function highlight(text,query) {
  const words=splitKeywords(query).filter(Boolean)
  if(!words.length)return text
  const escaped=words.map(word=>Array.from(word,c=>'\\^$.*+?()[]{}|'.includes(c)?'\\'+c:c).join(''))
  return String(text||'').split(new RegExp('('+escaped.join('|')+')','gi')).map((s,i)=>i%2?<mark key={i}>{s}</mark>:s)
}
export default function Detail({tid,back}) {
  const [filters,setFilters]=useState(defaults)
  const [draft,setDraft]=useState(defaults)
  const [open,setOpen]=useState(false)
  const [page,setPage]=useState(1)
  const [reload,setReload]=useState(0)
  const [data,setData]=useState(null)
  const [error,setError]=useState('')
  const [finishedKey,setFinishedKey]=useState('')
  const query=new URLSearchParams({tid,page,...filters}).toString()
  const requestKey=query+'#'+reload
  const loading=finishedKey!==requestKey
  const {run,running,progress}=useCommentTask(tid)
  useEffect(()=>{
    const ctrl=new AbortController()
    requestJson('/api/thread?'+query,{signal:ctrl.signal})
      .then(result=>{if(!ctrl.signal.aborted){setData(result);setError('')}})
      .catch(err=>{if(!ctrl.signal.aborted)setError(err.message)})
      .finally(()=>{if(!ctrl.signal.aborted)setFinishedKey(requestKey)})
    return ()=>ctrl.abort()
  },[query,requestKey])
  async function fetchComments(){
    try{if(await run()){setPage(1);setReload(v=>v+1)}}catch(err){if(err.name!=='AbortError')setError(err.message)}
  }
  const thread=data?.thread
  const pages=Math.max(1,Math.ceil((data?.total||0)/filters.page_size))
  return <><Bar back={back} title="帖子详情"/><Body>
    {error&&<Notice>{error} <button onClick={()=>setReload(v=>v+1)}>重新加载</button></Notice>}
    {loading&&!thread&&<LoadingContent variant="detail" rows={4}/>}
    {thread&&<>
      <h2 className="ty-detail-heading">{thread.title}</h2>
      <div className="ty-meta">{[thread.forum_name||'fid '+thread.fid,thread.author,thread.posted_at].filter(Boolean).join('　')}</div>
      <div className="ty-read-counts">{[['回复',thread.reply_count],['浏览',thread.view_count]].map(([label,value])=><div key={label}>{label}<b>{Number(value||0).toLocaleString()}</b></div>)}</div>
      <KV label="原帖地址"><a href={thread.official_url} target="_blank" rel="noreferrer">打开原帖 <LinkOutline className="ty-icon" aria-hidden="true"/></a></KV>
      <Section title="评论" action={<button onClick={()=>{setDraft(filters);setOpen(true)}}>筛选</button>}/>
      {filters.q||filters.exclude_q?<Notice>{[filters.q&&'包含 '+filters.q,filters.exclude_q&&'排除 '+filters.exclude_q].filter(Boolean).join(' · ')}</Notice>:null}
      <div aria-busy={loading}>{(data.comments||[]).map((c,i)=><article className="ty-comment" key={c.pid??i}>
        <strong>{c.author||'匿名'}</strong> <small> #{(page-1)*filters.page_size+i+1}</small>
        <p>{highlight(c.content_text,filters.q)}</p><small>{c.posted_at}</small>
      </article>)}</div>
      {!data.comments?.length&&!loading&&<Notice>{data.total_comments?'没有符合条件的评论':'本地还没有评论'}</Notice>}
      {pages>1&&<nav className="ty-read-pages"><button disabled={page===1||loading} onClick={()=>setPage(n=>n-1)}>上一页</button><span>{page} / {pages}</span><button disabled={page>=pages||loading} onClick={()=>setPage(n=>n+1)}>下一页</button></nav>}
      <button className="ty-link" disabled={running} onClick={fetchComments}>{running?'正在抓取评论…':data.total_comments?'更新评论':'抓取评论'}</button>
      {running&&<Notice>{progress.total_pages?'已处理 '+progress.completed_pages+' / '+progress.total_pages+' 页':'正在读取分页信息…'}</Notice>}
    </>}</Body>
    {open&&<Sheet title="筛选评论" onClose={()=>setOpen(false)} footer={<><button onClick={()=>setDraft(defaults)}>重置</button><Primary onClick={()=>{setFilters(draft);setPage(1);setOpen(false)}}>应用筛选</Primary></>}>
      {[['q','包含关键词'],['exclude_q','排除关键词']].map(([key,label])=><Field key={key} label={label}><Input value={draft[key]} onChange={v=>setDraft({...draft,[key]:v})}/></Field>)}
      <Choice label="每页评论" value={draft.page_size} options={COMMENT_PAGE_SIZE_OPTIONS.map(({value,label})=>[value,label])} onChange={v=>setDraft({...draft,page_size:+v})}/>
    </Sheet>}</>
}
