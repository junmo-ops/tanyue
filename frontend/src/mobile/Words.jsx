import { RedoOutline } from 'antd-mobile-icons'
import { useState,useEffect } from 'react'
import { LoadingContent } from '../Loading.jsx'
import { requestJson } from '../api/client.js'
import { Bar,Section,Notice,Body,Chip,Tools } from './ui.jsx'
import './discovery.css'
let batch
export default function Words({go,back}){
  const [words,setWords]=useState(batch)
  const [revision,setRevision]=useState(0)
  const [error,setError]=useState('')
  const [loading,setLoading]=useState(!batch)
  useEffect(()=>{
    if(batch&&!revision)return
    const controller=new AbortController()
    requestJson('/api/title-words?mode=random',{signal:controller.signal}).then(data=>{
      if(!controller.signal.aborted){batch=data.items;setWords(batch)}
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message)}).finally(()=>{if(!controller.signal.aborted)setLoading(false)})
    return ()=>controller.abort()
  },[revision])
  return <><Bar title="随机发现" back={back} right={<button disabled={loading} onClick={()=>{setError('');setLoading(true);setRevision(n=>n+1)}}>换一批 <RedoOutline className="ty-icon" aria-hidden="true"/></button>}/>
    <Body><Section title="从一个词开始"/><Notice>点选关键词，查看相关帖子。</Notice>
      {error&&<Notice>{error}</Notice>}{loading&&!words&&<LoadingContent label="正在加载词语" variant="tags"/>}
      <div className="ty-discovery-words"><Tools>{words?.map(({word})=><Chip key={word} onClick={()=>go('/?'+new URLSearchParams({view:'all',q:word}))}>{word}</Chip>)}</Tools></div>
      {words?.length===0&&<Notice>暂无可推荐的词语。</Notice>}
    </Body></>
}
