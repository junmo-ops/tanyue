import { RightOutline } from 'antd-mobile-icons'
import { useState } from 'react'
import { LoadingContent } from '../Loading.jsx'
import Input from 'antd-mobile/es/components/input'
import Choice from './Choice.jsx'
import { siteUrl } from '../api/site.js'
import { Bar,Body,Tools,Chip,Tabs,Section,KV,Field,Row,Notice,Sheet,Primary, Chevron } from './ui.jsx'
import { insightsUrl,insightResultsUrl,parseInsightsState } from '../features/threads/insightState.js'
import { hotPeriodRange,MAX_HOT_PERIOD } from '../features/threads/filters.js'
import useInsights from '../features/threads/useInsights.js'
import useDiscoveryData from './useDiscoveryData.js'
import './discovery.css'

const tabs=[['missed','漏看'],['growth','增长'],['overview','概览'],['authors','作者'],['topics','话题']]
const num=value=>Number(value||0).toLocaleString()
function Threads({items=[],go,seen,onSeen,growth=false}){
  if(!items.length)return <Notice>当前范围没有符合条件的帖子。</Notice>
  return items.map(thread=>{
    const localPath='/thread/'+encodeURIComponent(thread.tid)
    const alreadySeen=seen[thread.tid]||Number(thread.seen)
    const markRead=()=>{if(!alreadySeen)onSeen(thread.tid)}
    return <Row key={thread.tid} className="ty-insight-thread"
      title={<a href={thread.official_url||siteUrl(localPath)} target={thread.official_url?'_blank':undefined}
        rel="noreferrer" onClick={markRead}>{thread.title}</a>}
      meta={[thread.forum_name,thread.posted_at?.slice(0,10),alreadySeen?'已看':'',growth?'浏览 +'+num(thread.view_growth):''].filter(Boolean).join('　')}
      end={<button type="button" className="ty-insight-comments" aria-label={'查看本地评论：'+thread.title}
        onClick={()=>{markRead();go(localPath)}}>{growth?'回复 +'+num(thread.reply_growth):num(thread.reply_count)+' 回复'}</button>}/>
  })
}
function Results({selection,page,go,back,forums,onPage,seen,onSeen}){
  const {fid,q,authorId,dateFrom,dateTo,hideSeen}=selection
  const query=new URLSearchParams({page,page_size:20,sort:'reply_count',order:'desc',fid,q,author_id:authorId,posted_date_from:dateFrom,posted_date_to:dateTo,hide_seen:hideSeen?'1':'0'})
  const {data,error,retry}=useDiscoveryData('/api/threads?'+query)
  const forum=forums.find(f=>String(f.fid)===String(fid))?.forum_name||fid||'全部板块'
  return <><Bar title="分析结果" back={back}/><Tools>{[dateFrom.slice(5)+' — '+dateTo.slice(5),forum,hideSeen?'尚未看过':'',q,selection.authorName].filter(Boolean).map((s,i)=><span key={i} className="ty-chip"><span>{s}</span></span>)}</Tools><Body>
    <Section title={hideSeen?'漏看精选':'相关帖子'} action={data&&'共 '+num(data.total)+' 篇'}/>
    {error?<Notice>{error} <button onClick={retry}>重试</button></Notice>:!data?<LoadingContent/>:<><Threads items={data.items} {...{go,seen,onSeen}}/>{data.total>20&&<div className="ty-pager"><button className="ty-link" disabled={page<=1} onClick={()=>onPage(page-1)}>上一页</button><span>{page} / {Math.ceil(data.total/20)}</span><button className="ty-link" disabled={page*20>=data.total} onClick={()=>onPage(page+1)}>下一页</button></div>}</>}
  </Body></>
}
function Scope({filters,forums,close,apply}){
  const [days,setDays]=useState(String(filters.hot_days)),[fid,setFid]=useState(filters.fid),[period,setPeriod]=useState(filters.hot_period||0)
  const valid=Number.isInteger(+days)&&+days>=1&&+days<=365
  const range=hotPeriodRange({...filters,hot_days:valid?+days:filters.hot_days,hot_period:period})
  return <Sheet title="分析范围" onClose={close} footer={<Primary disabled={!valid} onClick={()=>apply({hot_days:+days,fid,hot_period:period})}>应用范围</Primary>}>
    <Choice label="板块" value={fid} options={[['','全部板块'],...forums.map(f=>[f.fid,f.forum_name])]} onChange={setFid}/>
    <Tools>{[3,5,7,14].map(d=><Chip active={+days===d} key={d} onClick={()=>setDays(String(d))}>{d} 天</Chip>)}</Tools>
    <Field label="每期天数（1–365）"><Input type="number" inputMode="numeric" min={1} max={365} value={days} onChange={setDays}/></Field>
    <div className="ty-pager"><button className="ty-link" disabled={period>=MAX_HOT_PERIOD} onClick={()=>setPeriod(period+1)}>上一期</button><span>{range.from.slice(5)} — {range.to.slice(5)}</span><button className="ty-link" disabled={!period} onClick={()=>setPeriod(period-1)}>下一期</button></div>
    <button className="ty-link" onClick={()=>apply({hot_days:valid?+days:filters.hot_days,hot_period:0,hot_anchor:'',fid})}>回到最近</button>
  </Sheet>
}
export default function Insights({location,go,back,forums,seen,onSeen}){
  const url=new URL(location,window.location.origin)
  if(!url.searchParams.has('days'))url.searchParams.set('days','7')
  const state=parseInsightsState(url)
  const {filters,page,selection}=state
  const tab=url.searchParams.has('tab')?state.tab:'overview'
  const {data,error,loading,refresh}=useInsights(filters,{active:!selection})
  const [scope,setScope]=useState(false)
  const range=hotPeriodRange(filters)
  const openTab=id=>go(insightsUrl(filters,id),{replace:true})
  const explore=values=>go(insightResultsUrl(filters,tab,{fid:filters.fid,dateFrom:range.from,dateTo:range.to,...values}))
  const props={go,seen,onSeen}
  if(selection)return <Results {...props} {...{selection,page,forums}} back={back} onPage={next=>go(insightResultsUrl(filters,tab,selection,next),{replace:true})}/>
  const overview=data?.overview
  const maximum=Math.max(1,...(overview?.daily||[]).map(item=>item.count))
  return <><Bar title="数据分析" back={back} right={<button onClick={()=>setScope(true)}>{filters.hot_period?'每期':'近'} {filters.hot_days} 天 <Chevron/></button>}/>
    <Tabs items={tabs} value={tab} onChange={openTab}/><Body>
      {error&&<Notice>{error} <button onClick={refresh}>重试</button></Notice>}{loading&&!data&&<LoadingContent label="正在整理本期数据"/>}
      {data&&<>
        {tab==='overview'&&<>
          <Section title="本期概览" action={range.from.slice(5)+' — '+range.to.slice(5)}/>
          <div className="ty-figures"><button onClick={()=>explore({})}><small>收录新帖</small><strong>{num(overview.total)}</strong></button><button onClick={()=>explore({hideSeen:true})}><small>尚未看过</small><strong>{num(overview.unseen)}</strong></button><div><small>感兴趣</small><strong>{num(overview.liked)}</strong></div></div>
          <Section title="每日新增"/><div className="ty-chart">{overview.daily.map(d=><button key={d.date} aria-label={d.date+'，'+num(d.count)+' 篇'} onClick={()=>explore({dateFrom:d.date,dateTo:d.date})}><i style={{height:(d.count?Math.max(3,d.count/maximum*100):0)+'%'}}/></button>)}</div>
          <div className="ty-chart-axis"><span>{range.from.slice(5)}</span><span>{range.to.slice(5)}</span></div>
          <Section title="漏看精选" action={<button onClick={()=>openTab('missed')}>查看全部 <RightOutline className="ty-icon" aria-hidden="true"/></button>}/><Threads items={data.missed.items.slice(0,4)} {...props}/>
          <Section title="板块分布"/>{overview.forums.map(f=><KV key={f.fid} label={f.forum_name}><button className="ty-link" onClick={()=>explore({fid:f.fid})}>{num(f.count)} 篇 <RightOutline className="ty-icon" aria-hidden="true"/></button></KV>)}
        </>}
        {tab==='missed'&&<><Section title="漏看精选" action={<button onClick={()=>explore({hideSeen:true})}>查看全部未看 <RightOutline className="ty-icon" aria-hidden="true"/></button>}/><Threads items={data.missed.items} {...props}/></>}
        {tab==='growth'&&<><Section title="热度增长" action={num(data.growth.eligible_count)+' 篇可比较'}/><Threads items={data.growth.items} growth {...props}/><Notice>{data.growth.note}</Notice></>}
        {tab==='topics'&&<><Section title="话题变化"/>{!data.topics.length&&<Notice>本期暂无占比上升的话题。</Notice>}{data.topics.map(t=><section key={t.word}><Section title={t.word} action={<button onClick={()=>explore({q:t.word})}>相关帖子 <RightOutline className="ty-icon" aria-hidden="true"/></button>}/><Notice>本期 {num(t.count)} 篇 · 占比增长 {Number(t.change_pp).toFixed(1)} 个百分点</Notice><Threads items={t.items} {...props}/></section>)}</>}
        {tab==='authors'&&<><Section title="作者发现"/>{!data.authors.length&&<Notice>本期没有符合条件的作者。</Notice>}{data.authors.map(a=><section key={a.author_id}><Section title={a.author||a.author_id} action={<button onClick={()=>explore({authorId:a.author_id,authorName:a.author})}>全部作品 <RightOutline className="ty-icon" aria-hidden="true"/></button>}/><Notice>{num(a.count)} 篇 · {num(a.liked_count)} 篇感兴趣 · 回复中位数 {num(a.median_replies)}</Notice><Threads items={a.items} {...props}/></section>)}</>}
        <button className="ty-link" disabled={loading} onClick={refresh}>刷新分析</button>
      </>}
    </Body>{scope&&<Scope filters={filters} forums={forums} close={()=>setScope(false)} apply={values=>{setScope(false);go(insightsUrl({...filters,...values},tab),{replace:true})}}/>}</>
}
