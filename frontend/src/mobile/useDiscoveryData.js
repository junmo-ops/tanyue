import { useEffect, useState } from 'react'
import { requestJson } from '../api/client.js'

export default function useDiscoveryData(url, poll) {
  const [state,setState] = useState(null)
  const [revision,setRevision] = useState(0)
  useEffect(()=>{
    const controller = new AbortController()
    let timer
    async function load(){
      try {
        const data = await requestJson(url,{signal:controller.signal})
        if(controller.signal.aborted) return
        setState({url,data})
        if(poll?.(data)) timer=setTimeout(load,2000)
      } catch(error) {
        if(!controller.signal.aborted) setState({url,error:error.message})
      }
    }
    if(url)load()
    return ()=>{controller.abort();clearTimeout(timer)}
  },[url,poll,revision])
  return {...(state?.url===url?state:{}),retry:()=>setRevision(n=>n+1)}
}
