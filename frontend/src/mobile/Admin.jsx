import { useEffect, useRef, useState } from 'react'
import Switch from 'antd-mobile/es/components/switch'
import { postJson, requestJson } from '../api/client.js'
import { Bar, Body, Tabs, Tools, Chip, Section, Row, KV, Sheet, Primary, Notice } from './ui.jsx'
import { Entry, TaskFields, PlanFields, ScheduleFields } from './AdminForms.jsx'
import Choice from './Choice.jsx'
import { kinds, nextKey, settingsFields } from './AdminData.js'
import './Admin.css'

const views=[['overview','概览'],['records','任务记录'],['plans','方案与定时'],['settings','设置']]
const filters=[['all','全部'],['active','进行中'],['errors','异常'],['history','历史']]
const states={succeeded:'已完成',failed:'失败',partial:'部分完成',interrupted:'服务中断',queued:'排队中',running:'运行中',stopping:'正在停止',cancelled:'已停止'}
const active=j=>['queued','running','stopping'].includes(j.status)
const failed=j=>['partial','failed','interrupted'].includes(j.status)
const jobsUrl='/api/crawl-jobs',adminUrl='/api/crawl-admin'
const jobDate=value=>new Date(value.replace(' ','T')+'Z')
const dayLabel=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric'})
const clock=new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',hour:'2-digit',minute:'2-digit',hourCycle:'h23'})
const dateKey=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai'})
const time=value=>value?shortDate(value)+' '+clock.format(jobDate(value)):'—'
function duration(seconds){
  return seconds<60?seconds+' 秒':Math.floor(seconds/60)+' 分 '+seconds%60+' 秒'
}
const clean=step=>Object.fromEntries(Object.entries(step).filter(([key,value])=>key!=='_key'&&value!==''&&value!=null))
function summary(j){const p=j.progress;if(!p)return states[j.status];const errors=p.failed?'，失败 '+p.failed:''
 if(j.kind==='rankings')return '保存 '+(p.completed||0)+' 份榜单'+errors
 if(j.kind==='comments')return '保存 '+(p.saved_comments||0)+' 条评论'+errors
 if(j.kind==='details')return '完成 '+(p.completed||0)+errors
 return '新增 '+(p.new||0)+'，更新 '+(p.updated||0)+errors}
function shortDate(value){
 const date=jobDate(value),now=Date.now()
 if(dateKey.format(date)===dateKey.format(now))return '今日'
 if(dateKey.format(date)===dateKey.format(now-86400000))return '昨日'
 return dayLabel.format(date)
}
function Badge({job}){return <span className={'ta-status '+(failed(job)?'warn':'')}>{states[job.status]||job.status}</span>}
function previewSummary(value,forums){
 if(value.kind==='sync'){
  const selected=value.fids?.length===forums.length?'全部板块':value.fids?.length+' 个板块'
  return selected+' · '+(value.pages?'共 '+value.pages+' 页':'自动增量')
 }
 if(value.kind==='comments')return '仅处理已开启抓评的帖子'
 return '预计 '+value.target_count+(value.kind==='rankings'?' 份榜单':' 个待处理帖子')
}
function Preview({value,forums}){
 const names=new Map(forums.map(f=>[String(f.value),f.label]))
 return <><KV label="任务类型">{kinds[value.kind]}</KV>{value.kind==='sync'?<><KV label="采集板块">{value.fids.map(id=>names.get(String(id))||id).join('、')}</KV><KV label="抓取方式">{value.pages?`共 ${value.pages} 页`:'自动增量'}</KV></>:<KV label="预计处理">{value.target_count} {value.kind==='rankings'?'份榜单':'个帖子'}</KV>}
 {!value.cookie_available&&!value.anonymous_allowed&&<Notice>Cookie 不可用，请先更新登录信息。</Notice>}</>
}
function JobInfo({job,action,back,busy,observedAt}){
 const p=job.progress||{},log=useRef(null)
 const [follow,setFollow]=useState(true),[copied,setCopied]=useState('')
 useEffect(()=>{if(follow&&log.current)log.current.scrollTop=log.current.scrollHeight},[job.log,follow])
 return <><Row title={<>{kinds[job.kind]} <Badge job={job}/></>}/>
 <div className="ta-metrics">{(job.kind==='rankings'?[['已保存',p.completed],['目标',p.total],['失败',p.failed]]:[['新增',p.new],['更新',p.updated],['失败',p.failed]]).map(([l,v])=><div key={l}><small>{l}</small><strong>{v||0}</strong></div>)}</div>
 <KV label="开始时间">{time(job.started_at)}</KV>
 {job.started_at&&<KV label="耗时">{duration(Math.max(0,Math.round(((job.finished_at?jobDate(job.finished_at):observedAt)-jobDate(job.started_at))/1000)))}</KV>}
 <details className="ta-disclosure"><summary className="ta-line">执行信息 <span>展开 ﹀</span></summary><KV label="提交时间">{time(job.created_at)}</KV><KV label="结束时间">{time(job.finished_at)}</KV><KV label="执行进度">{p.completed||0}{p.total_known?' / '+p.total:''}</KV>{job.kind==='comments'&&<KV label="保存评论">{p.saved_comments||0}</KV>}
 <KV label="采集范围">{Object.entries(job.params||{}).map(([k,v])=>({fid:'板块',pages:'页数',start_page:'起始页',limit:'上限',tids:'指定帖子'}[k]||k)+' '+v).join(' · ')||'使用提交时的配置'}</KV></details>
 {p.errors?.map((e,i)=><Notice key={i}>{[e.target,e.page&&'第 '+e.page+' 页',e.error].filter(Boolean).join(' · ')}</Notice>)}
 <details className="ta-disclosure"><summary className="ta-line">运行日志 <span>展开 ﹀</span></summary><KV label="跟随最新"><Switch checked={follow} onChange={setFollow}/></KV><button className="ty-link" onClick={async()=>{try{await navigator.clipboard.writeText(job.log||'');setCopied('已复制')}catch{setCopied('请长按日志复制')}}}>{copied||'复制日志'}</button><pre ref={log} className="ta-log">{job.log||'暂无日志'}</pre></details>
 <div className="ta-actions"><button onClick={back}>查看帖子列表</button>{(active(job)||failed(job)||job.status==='cancelled')&&<button disabled={busy||job.status==='stopping'} onClick={()=>action(active(job)?'stop':'resume',job.id)}>{active(job)?job.status==='queued'?'取消排队':'停止任务':'继续未完成'}</button>}</div></>
}
function useSubmitGuard(){
 const lock=useRef(false)
 return {
   acquire(){if(lock.current)return false;lock.current=true;return true},
   release(){lock.current=false}
 }
}
export default function Admin({back}){
 const [view,setView]=useState('overview'),[tab,setTab]=useState('plans'),[filter,setFilter]=useState('all'),[page,setPage]=useState(1)
 const [jobs,setJobs]=useState(null),[admin,setAdmin]=useState(null),[offline,setOffline]=useState('')
 const [panel,setPanel]=useState(''),[draft,setDraft]=useState({}),[preview,setPreview]=useState([]),[id,setId]=useState('')
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false),guard=useSubmitGuard()
 const [settings,setSettings]=useState(null),[setting,setSetting]=useState(null),[revision,refresh]=useState(0)
 useEffect(()=>{const ctrl=new AbortController();let timer
 async function load(){try{const [j,a]=await Promise.all([requestJson(jobsUrl,{signal:ctrl.signal}),requestJson(adminUrl,{signal:ctrl.signal})]);if(!ctrl.signal.aborted){setJobs({...j,observedAt:Date.now()});setAdmin(a);setOffline('')}}catch(e){if(!ctrl.signal.aborted)setOffline(e.message)}finally{if(!ctrl.signal.aborted)timer=setTimeout(load,3000)}}
 load();return()=>{ctrl.abort();clearTimeout(timer)}},[revision])
 const list=jobs?.items||[],forums=jobs?.forums||[],presets=admin?.presets||[],schedules=admin?.schedules||[]
 const running=list.filter(active),errors=list.filter(failed),history=list.filter(j=>!active(j)),current=list.find(j=>j.id===id)
 const filtered={all:list,active:running,errors,history}[filter],totalPages=Math.max(1,Math.ceil(filtered.length/8)),shownPage=Math.min(page,totalPages)
 const shown=view==='overview'?history.slice(0,4):filtered.slice((shownPage-1)*8,shownPage*8)
 const groups=Object.groupBy?Object.groupBy(shown,j=>shortDate(j.created_at)):shown.reduce((g,j)=>{(g[shortDate(j.created_at)]??=[]).push(j);return g},{})
 function open(which,value={}){setError('');setNotice('');setDraft(value);setPanel(which)}
 function close(){if(!busy){setPanel('');setError('')}}
 async function run(fn,success){if(!guard.acquire())return;setBusy(true);setError('');setNotice('')
 try{const response=await fn();success?.(response);refresh(n=>n+1)}catch(e){setError(e.message)}finally{guard.release();setBusy(false)}}
 const finish=text=>()=>{setPanel('');setNotice(text)}
 const post=(path,value,success)=>run(()=>postJson(path,value),success)
 function record(j){setId(j.id);open('job')}
 function showRecords(f){setView('records');setFilter(f);setPage(1)}
 function editPlan(p){open('plan',{id:p?.id,name:p?.name||'',steps:(p?.steps||[{kind:'sync'}]).map(s=>({...s,_key:nextKey()}))})}
 function editSchedule(s){open('schedule',s?{...s,enabled:!!s.enabled}:{name:'',preset_id:'',mode:'daily',daily_time:'23:30',every_minutes:60,enabled:false,busy_policy:'skip'})}
 function previewPlan(p){run(()=>Promise.all(p.steps.map(s=>postJson(jobsUrl+'/preview',s))),values=>{open('run',p);setPreview(values)})}
 function queued(value){setId(value.id||value.ids?.[0]||'');setPanel('job');setNotice('已加入采集队列')}
 const config=settings||admin?.settings
 const link=(text,fn,disabled=false)=><button type="button" className="ty-link" disabled={disabled||busy} onClick={fn}>{text}</button>
 const jobRow=j=><Row key={j.id} title={<>{kinds[j.kind]} <Badge job={j}/></>} meta={time(j.created_at)+' · '+summary(j)} end="详情 ›" onClick={()=>record(j)}/>
 const errorsBar=offline&&<Notice>暂时无法更新 · {offline}</Notice>
 const settingsRow=f=><div className="ta-line" key={f[1]}><span>{f[2]}</span>{link(String(config[f[0]][f[1]])+' ›',()=>{setSetting(f);open('setting',{value:config[f[0]][f[1]]})})}</div>
 function setOption(section,key,value){setSettings({...config,[section]:{...config[section],[key]:value}})}
 const panelNames={new:'新建采集',preview:'确认采集范围',run:'运行'+draft.name,job:'任务详情',plan:draft.id?'编辑采集方案':'新建采集方案',schedule:draft.id?'编辑定时计划':'新建定时计划',more:'更多操作',delete:draft.type==='presets'?'删除采集方案？':'删除定时计划？',setting:setting?.[2]}
 const buttons={
 new:['预览采集范围',()=>post(jobsUrl+'/preview',clean(draft),result=>{setPreview([result]);setPanel('preview')})],
 preview:['加入采集队列',()=>post(jobsUrl,clean(draft),queued)],
 run:['加入采集队列',()=>post(adminUrl+'/presets/run',{id:draft.id},queued)],
 plan:['保存方案',()=>post(adminUrl+'/presets',{...draft,steps:draft.steps.map(clean)},finish('方案已保存'))],
 schedule:['保存计划',()=>post(adminUrl+'/schedules',draft,finish('计划已保存'))],
 delete:[draft.type==='presets'?'删除方案':'删除计划',()=>post(adminUrl+'/'+draft.type+'/delete',{id:draft.id},finish('已删除'))],
 setting:['应用',()=>{const [s,k,,min,max,step]=setting;const n=draft.value;if(typeof n!=='number'||n<min||n>max||(!step&&!Number.isInteger(n))){setError('请输入有效范围内的数值');return}setOption(s,k,n);close()}]
 }
 return <><Bar title="采集管理" back={back} right={['overview','records'].includes(view)&&<Primary disabled={!admin||busy} onClick={()=>open('new',{kind:'sync'})}>＋ 新建采集</Primary>}/>
 <Tabs value={view} items={views} onChange={v=>{setView(v);setNotice('');setError('')}}/>
 <Body className={'ta-body'+(view==='settings'?' ta-settings':'')}>{errorsBar}{notice&&<Notice>{notice}</Notice>}{error&&!panel&&<Notice>{error}</Notice>}{!admin&&!offline&&<Notice>正在读取采集状态…</Notice>}
 {view==='overview'&&<><KV label={offline?'连接异常':jobs?'服务已连接':'连接中'}>执行中 {running.filter(j=>j.status!=='queued').length} · 等待 {running.filter(j=>j.status==='queued').length}</KV>
 {errors.length>0&&<button className="ta-warn" onClick={()=>showRecords('errors')}>{errors.length} 条异常待查看 <span>›</span></button>}
 {running.length>0&&<><Section title="当前队列" action={link('查看队列 ›',()=>showRecords('active'))}/>{jobRow(running[0])}</>}
 <Section title="快捷采集" action={link('管理方案 ›',()=>{setTab('plans');setView('plans')})}/>
 {presets.slice(0,3).map(p=><div className="ta-line" key={p.id}><span>{p.name}</span>{link('预览并运行 ›',()=>previewPlan(p))}</div>)}
 {!presets.length&&admin&&<Notice>暂无常用方案</Notice>}
 <Section title="最近采集结果" action={link('全部记录 ›',()=>showRecords('all'))}/>{shown.map(jobRow)}{jobs&&!shown.length&&<Notice>还没有采集记录</Notice>}</>}
 {view==='records'&&<><Tools>{filters.map(([v,l])=><Chip key={v} active={filter===v} onClick={()=>{setFilter(v);setPage(1)}}>{l}</Chip>)}</Tools>
 {filter==='errors'&&shown.length>0?<><Section title="异常记录" action={<small>{filtered.length} 条</small>}/>{shown.map(jobRow)}</>:Object.entries(groups).map(([date,items])=><section key={date}><Section title={date} action={<small>{items.length} 条</small>}/>{items.map(jobRow)}</section>)}
 {!shown.length&&jobs&&<Notice>没有符合条件的任务</Notice>}{totalPages>1&&<div className="ta-line">{link('上一页',()=>setPage(shownPage-1),shownPage<=1)}{shownPage} / {totalPages}{link('下一页',()=>setPage(shownPage+1),shownPage>=totalPages)}</div>}</>}
 {view==='plans'&&<><Tabs items={ [['plans','常用方案'],['schedules','定时计划']] } value={tab} onChange={setTab}/>
 {tab==='plans'?<div className="ta-section-actions">{link('＋ 新建方案',()=>editPlan(),!admin)}</div>:<Section title="定时计划" action={link('＋ 新建计划',()=>editSchedule(),!admin)}/>}
 {(tab==='plans'?presets:schedules).map(r=><article className="ta-record" key={r.id}><b>{r.name}</b> {tab==='schedules'&&<span className="ta-status">{r.enabled?'已启用':'已停用'}</span>}
 {tab==='plans'?<p className="ta-note">{r.steps.map(s=>kinds[s.kind]).join(' → ')}</p>:<><p className="ta-note">{r.mode==='daily'?'每天 '+r.daily_time+' · 北京时间':'每 '+r.every_minutes+' 分钟'}</p><KV label="执行方案">{presets.find(p=>p.id===r.preset_id)?.name||'—'}</KV><KV label="下次执行">{r.enabled&&r.next_run?dayLabel.format(r.next_run*1000)+' '+clock.format(r.next_run*1000):'—'}</KV></>}
 <div className="ta-actions">{tab==='plans'?<>{link('预览并运行',()=>previewPlan(r))}{link('编辑',()=>editPlan(r))}</>:link('编辑计划',()=>editSchedule(r))}
 <button aria-label={r.name+'的更多操作'} onClick={()=>open('more',{type:tab==='plans'?'presets':'schedules',id:r.id,name:r.name,schedule:tab==='schedules'?r:null})}>{tab==='schedules'?'更多 ···':'···'}</button></div></article>)}
 {admin&&!(tab==='plans'?presets:schedules).length&&<Notice>{tab==='plans'?'暂无常用方案':'暂无定时计划'}</Notice>}</>}
 {view==='settings'&&config&&<><Section title="采集配置"/>{settingsFields.filter(f=>f[0]==='list_sync').map(settingsRow)}
 <details className="ta-disclosure"><summary className="ta-line">帖子详情与评论 <span>展开 ﹀</span></summary>{settingsFields.filter(f=>f[0]==='details'||f[0]==='comments').map(settingsRow)}
 <Choice inline label="每帖评论页数" value={config.comments.pages} options={['all',1,3,5,10,20,50,100].map(v=>[v,v==='all'?'全部页面':v+' 页'])} onChange={v=>setOption('comments','pages',v==='all'?v:Number(v))}/>
 <KV label="重新抓取已完成评论"><Switch checked={config.comments.refresh_existing} onChange={v=>setOption('comments','refresh_existing',v)}/></KV></details>
 <Section title="网络与登录"/><details className="ta-disclosure"><summary className="ta-line">网络与重试 <span>展开 ﹀</span></summary>{settingsFields.filter(f=>f[0]==='network').map(settingsRow)}</details>
 <div className="ta-line"><span>Cookie 与站点访问</span>{link('检查 ›',()=>post(adminUrl+'/check-login',{},r=>setNotice(r.message)))}</div><p className="ta-note">配置将在下次提交任务时生效。</p>
 <div className="ta-settings-save"><small>{settings?'尚未保存':'已同步'}</small><Primary disabled={!settings||busy} onClick={()=>post(adminUrl+'/settings',settings,()=>{setSettings(null);setNotice('配置已保存')})}>保存配置</Primary></div></>}
 </Body>
 {panel&&<Sheet title={panelNames[panel]} onClose={close} footer={buttons[panel]&&<>{link(panel==='preview'?'返回修改':'取消',()=>panel==='preview'?setPanel('new'):close())}<Primary className={panel==='delete'?'ta-danger':''} disabled={busy} onClick={buttons[panel][1]}>{buttons[panel][0]}</Primary></>}>
 {error&&<Notice>{error}</Notice>}
 {panel==='new'&&<TaskFields step={draft} set={setDraft} forums={forums}/>}
 {panel==='plan'&&<PlanFields draft={draft} set={setDraft} forums={forums}/>}
 {panel==='schedule'&&<ScheduleFields draft={draft} set={setDraft} presets={presets}/>}
 {panel==='setting'&&<Entry type="number" label={setting[2]} value={draft.value} min={setting[3]} max={setting[4]} step={setting[5]||1} onChange={value=>setDraft({value})}/>}
 {panel==='preview'&&preview[0]&&<Preview value={preview[0]} forums={forums}/>}
 {panel==='run'&&preview.map((value,index)=><section key={index}>
   <Row title={kinds[value.kind]} meta={previewSummary(value,forums)}/>
   {!value.cookie_available&&!value.anonymous_allowed&&<Notice>Cookie 不可用，请先更新登录信息。</Notice>}
 </section>)}
 {['preview','run'].includes(panel)&&preview[0]?.note&&<p className="ta-note">{preview[0].note}</p>}
 {panel==='job'&&(current?<JobInfo observedAt={jobs.observedAt} job={current} back={back} busy={busy} action={(a,id)=>post(jobsUrl+'/'+a,{id},a==='resume'?queued:()=>setNotice('已发送停止请求'))}/>:<Notice>正在读取任务记录…</Notice>)}
 {panel==='more'&&<>{draft.schedule&&<><KV label="最近触发">{draft.schedule.last_result||'尚未触发'}</KV>{link(draft.schedule.enabled?'停用计划':'启用计划',()=>post(adminUrl+'/schedules',{...draft.schedule,enabled:!draft.schedule.enabled},finish('计划已更新')))}</>}{link('删除'+(draft.type==='presets'?'方案':'计划'),()=>setPanel('delete'))}</>}
 {panel==='delete'&&<Notice>将删除「{draft.name}」{draft.type==='presets'?'方案':'计划'}。</Notice>}
 </Sheet>}</>
}
