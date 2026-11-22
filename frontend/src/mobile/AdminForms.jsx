import Input from 'antd-mobile/es/components/input'
import Switch from 'antd-mobile/es/components/switch'
import { Field, KV, Section } from './ui.jsx'

import Choice from './Choice.jsx'
import { kinds, nextKey } from './AdminData.js'

export function Entry({label,value,onChange,type='text',...props}){
  return <Field label={label}><Input type={type} value={String(value??'')} onChange={text=>onChange(type==='number'&&text!==''?Number(text):text)} {...props}/></Field>
}
export function TaskFields({step,set,forums,showKind=true}){
  const update=(key,value)=>set({...step,[key]:value})
  return <>{showKind&&<Choice label="任务类型" value={step.kind} onChange={kind=>set({kind})} options={Object.entries(kinds)}/>}
    {step.kind==='sync'&&<><Choice inline={!showKind} label="板块" value={step.fid} options={[[ '', '全部已配置板块'],...forums.map(f=>[f.value,f.label])]} onChange={v=>update('fid',v)}/>
    <PageFields collapsed={showKind}><div className="ta-pair"><Entry type="number" label="抓取页数" placeholder="自动增量" value={step.pages} min={1} max={2000} onChange={v=>update('pages',v)}/><Entry type="number" label="起始页" placeholder="默认 1" value={step.start_page} min={1} max={100000} onChange={v=>update('start_page',v)}/></div></PageFields></>}
    {['details','comments'].includes(step.kind)&&<Entry type="number" label="处理上限" placeholder="使用采集配置" min={1} max={100000} value={step.limit} onChange={v=>update('limit',v)}/>}
    {step.kind==='details'&&<Entry label="指定帖子 ID（可选）" value={step.tids} placeholder="英文逗号分隔" onChange={v=>update('tids',v)}/>}
  </>
}
function PageFields({collapsed,children}){
  return collapsed?<details className="ta-disclosure"><summary className="ta-line">指定抓取页数与起始页 <span>展开 ﹀</span></summary>{children}</details>:children
}
export function PlanFields({draft,set,forums}){
  const replace=steps=>set({...draft,steps})
  const move=(i,j)=>{const steps=[...draft.steps];[steps[i],steps[j]]=[steps[j],steps[i]];replace(steps)}
  return <><Entry label="方案名称" value={draft.name} maxLength={60} onChange={name=>set({...draft,name})}/>
    <Section title="采集步骤" action={<small>{draft.steps.length} 步</small>}/>
    {draft.steps.map((step,i)=><section className="ta-step" key={step._key}>
      <div className="ta-stephead"><i>{String(i+1).padStart(2,'0')}</i><Choice compact label={`步骤 ${i+1} 任务类型`} value={step.kind} options={Object.entries(kinds)} onChange={kind=>replace(draft.steps.map((s,j)=>j===i?{kind,_key:s._key}:s))}/>{draft.steps.length>1&&<button type="button" onClick={()=>move(i,i?i-1:1)}>{i?'↑ 上移':'↓ 下移'}</button>}</div>
      {step.kind==='sync'?<TaskFields showKind={false} step={step} forums={forums} set={next=>replace(draft.steps.map((s,j)=>j===i?{...next,_key:s._key}:s))}/>:step.kind!=='rankings'&&<details><summary>{step.kind==='details'?'处理上限 · '+(step.limit||'使用采集配置'):'仅处理已开启抓评的帖子'} ›</summary>
        <TaskFields showKind={false} step={step} forums={forums} set={next=>replace(draft.steps.map((s,j)=>j===i?{...next,_key:s._key}:s))}/></details>}
      {draft.steps.length>1&&<details className="ta-step-more"><summary>步骤操作</summary><button className="ty-link" onClick={()=>replace(draft.steps.filter((_,j)=>i!==j))}>移除此步</button></details>}
    </section>)}
    <button className="ty-link" disabled={draft.steps.length>=10} onClick={()=>replace([...draft.steps,{kind:'details',_key:nextKey()}])}>＋ 添加步骤</button></>
}
export function ScheduleFields({draft,set,presets}){
 const update=(k,v)=>set({...draft,[k]:v})
 return <><Entry label="计划名称" value={draft.name} maxLength={60} onChange={v=>update('name',v)}/>
 <Choice label="执行方案" value={draft.preset_id} options={[[ '', '请选择方案'],...presets.map(p=>[p.id,p.name])]} onChange={v=>update('preset_id',v)}/>
 <div className="ta-pair"><Choice label="周期" value={draft.mode} options={ [['daily','每天'],['interval','固定间隔']] } onChange={v=>update('mode',v)}/>
 {draft.mode==='daily'?<Entry type="time" label="北京时间" value={draft.daily_time} onChange={v=>update('daily_time',v)}/>:<Entry type="number" label="间隔（分钟）" value={draft.every_minutes} min={5} max={43200} onChange={v=>update('every_minutes',v)}/>}</div>
 <Choice inline label="已有任务时" value={draft.busy_policy} options={ [['skip','跳过本次'],['queue','加入队列']] } onChange={v=>update('busy_policy',v)}/>
 <KV label="启用计划"><Switch checked={!!draft.enabled} onChange={v=>update('enabled',v)} aria-label="启用计划"/></KV></>
}
