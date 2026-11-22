import { useEffect, useState } from 'react'
import { requestJson } from '../../api/client.js'
import { hotPeriodRange, normalizeHotDays, normalizeHotPeriod } from './filters.js'

// Keep a small session snapshot so returning from results does not reshuffle it.
const snapshots = new Map()

export default function useInsights(filters, { active, preview = false, refreshKey = 0 }) {
  const [revision, setRevision] = useState(0)
  const range = hotPeriodRange(filters)
  const params = new URLSearchParams({
    days: normalizeHotDays(filters.hot_days), period: normalizeHotPeriod(filters.hot_period),
    anchor: range.anchor, fid: filters.fid || '', mode: preview ? 'preview' : 'full',
  })
  const url = `/api/insights?${params}`
  const key = `${url}:${refreshKey}:${revision}`
  const [result, setResult] = useState(() => snapshots.has(url) ? { ...snapshots.get(url), key } : null)
  useEffect(() => {
    if (!active || result?.key === key) return
    const controller = new AbortController()
    requestJson(url, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) {
        const next = { key, url, data }
        snapshots.delete(url)
        snapshots.set(url, next)
        if (snapshots.size > 12) snapshots.delete(snapshots.keys().next().value)
        setResult(next)
      }
    }).catch(error => {
      if (!controller.signal.aborted) setResult(previous => ({ key, url, error: error.message, data: previous?.url === url ? previous.data : null }))
    })
    return () => controller.abort()
  }, [active, key, url, result?.key])
  return {
    data: result?.url === url ? result.data : null,
    error: result?.key === key ? result.error : '',
    loading: active && result?.key !== key,
    refresh: () => setRevision(value => value + 1),
  }
}
