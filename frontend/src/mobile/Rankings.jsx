import { useState } from 'react'
import Calendar from 'antd-mobile/es/components/calendar'
import dayjs from 'dayjs'
import useDiscoveryData from './useDiscoveryData.js'
import { Bar,Tabs,Tools,Chip,Body,Notice,Sheet } from './ui.jsx'
import './discovery.css'

const metrics=[['replies','回复'],['views','查看'],['sharetimes','分享'],['favtimes','收藏'],['heats','热度']]
const periods=[['today','今日','当日'],['thisweek','本周','当周'],['thismonth','本月','当月'],['all','全部','全部']]
const beijing=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'})
const collecting=data=>['queued','running','stopping'].includes(data.job?.status)
export default function Rankings({location,go,back}){
  const params=new URL(location,window.location.origin).searchParams
  const metric=metrics.find(([id])=>id===params.get('metric'))||metrics[0]
  const period=periods.find(([id])=>id===params.get('period'))||periods[0]
  const snapshot=params.get('snapshot')||''
  const date=params.get('date')||''
  const base=new URLSearchParams({metric:metric[0],period:period[0]})
  const url='/api/rankings?'+base
  const listing=useDiscoveryData(url,collecting)
  const dates=new Map((listing.data?.snapshots||[]).map(s=>[beijing.format(new Date(s.captured_at)),String(s.id)]))
  const selectedId=snapshot||dates.get(date)||''
  const historical=Boolean(snapshot||date)
  const selected=useDiscoveryData(selectedId?url+'&snapshot='+encodeURIComponent(selectedId):null)
  const current=historical?selected:listing
  const data=current.data
  const selectedDate=date||(data?.snapshot?beijing.format(new Date(data.snapshot.captured_at)):'')
  const [open,setOpen]=useState(false)
  const [month,setMonth]=useState('')
  const calendarMonth=month||selectedDate.slice(0,7)||dayjs().format('YYYY-MM')
  function calendarCell(cell,{date}){
    const day=dayjs(date)
    if(day.format('YYYY-MM')===calendarMonth)return cell
    const sunday=day.subtract(day.day(),'day')
    const weekContainsMonth=[sunday,sunday.add(6,'day')].some(edge=>edge.format('YYYY-MM')===calendarMonth)
    return weekContainsMonth?<span className="adm-calendar-cell adm-calendar-cell-outside" aria-hidden="true"/>:null
  }
  function navigate(m,p,d=''){
    const query=new URLSearchParams({metric:m,period:p})
    if(d)query.set('date',d)
    go('/rankings?'+query,{replace:true})
  }
  return <><Bar title="排行榜" back={back} right={<button onClick={()=>{setMonth('');setOpen(true)}}>{selectedDate?dayjs(selectedDate).format('M 月 D 日'):'选择日期'}{historical?'快照':''} ﹀</button>}/>
    <Tabs items={metrics} value={metric[0]} onChange={m=>navigate(m,period[0],historical?selectedDate:'')}/>
    <Tools>{periods.map(([id,t,h])=><Chip key={id} active={period[0]===id} onClick={()=>navigate(metric[0],id,historical?selectedDate:'')}>{historical?h:t}</Chip>)}{historical&&<button className="ty-link" onClick={()=>navigate(metric[0],period[0])}>回到最新</button>}</Tools>
    <Body>{listing.error||current.error?<Notice>{listing.error||current.error} <button onClick={listing.error?listing.retry:current.retry}>重试</button></Notice>:!data?<Notice>{date&&listing.data&&!selectedId?'该日期没有这份榜单的快照':'正在读取榜单…'}</Notice>:null}
      {data?.entries.map(e=><a className="ty-ranked" key={e.tid} href={e.url} target="_blank" rel="noreferrer"><b>{String(e.rank).padStart(2,'0')}</b><div className="ty-row"><strong>{e.title}</strong><span className="ty-meta"><span>{e.forum||e.author_and_date}</span><em>{Number(e.value).toLocaleString()} {metric[1]}</em></span></div></a>)}
      {data&&!data.entries.length&&<Notice>{data.snapshot?'本期榜单暂无帖子':'暂无快照，可在采集管理中采集榜单。'}</Notice>}
      {listing.data&&collecting(listing.data)&&<Notice>已采集 {listing.data.job.completed} / {listing.data.job.total} 份</Notice>}
      {listing.data?.job?.error&&<Notice>{listing.data.job.error}</Notice>}
      {data?.source_url&&<a className="ty-link" href={data.source_url} target="_blank" rel="noreferrer">查看原榜 ↗</a>}
    </Body>{open&&<Sheet title="选择榜单日期" onClose={()=>setOpen(false)}>
      <Calendar className="ty-rank-calendar" onPageChange={(year,month)=>setMonth(year+'-'+String(month).padStart(2,'0'))}
        cellRender={calendarCell} selectionMode="single" allowClear={false} value={selectedDate?dayjs(selectedDate).toDate():null}
        shouldDisableDate={v=>!dates.has(dayjs(v).format('YYYY-MM-DD'))} onChange={v=>{navigate(metric[0],period[0],dayjs(v).format('YYYY-MM-DD'));setOpen(false)}}/>
      <Notice>仅可选择已有快照的日期 · 北京时间</Notice><button className="ty-link" onClick={()=>{navigate(metric[0],period[0]);setOpen(false)}}>回到最新</button>
    </Sheet>}</>
}
