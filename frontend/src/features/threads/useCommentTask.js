import { useEffect, useRef, useState } from 'react'
import { postJson, requestJson } from '../../api/client.js'

export default function useCommentTask(tid) {
  const controllerRef = useRef(null)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState({ status: 'idle', percent: 0 })
  useEffect(() => () => controllerRef.current?.abort(), [tid])

  const run = async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const { signal } = controller
    setRunning(true)
    setProgress({ status: 'queued', percent: 0 })
    try {
      let job = await postJson('/api/comment-jobs', { tid }, signal)
      while (!signal.aborted) {
        setProgress(job)
        if (job.status === 'failed') throw new Error(job.error || '评论抓取失败')
        if (job.status === 'fetched') return await requestJson(`/api/thread?tid=${encodeURIComponent(tid)}`, { signal })
        await new Promise(resolve => window.setTimeout(resolve, 1000))
        signal.throwIfAborted()
        job = await requestJson(`/api/comment-jobs?id=${encodeURIComponent(job.id)}`, { signal })
      }
    } finally {
      if (!signal.aborted) setRunning(false)
    }
  }
  return { run, running, progress }
}
