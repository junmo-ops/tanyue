import { useCallback, useEffect, useRef, useState } from 'react'
import { requestJson } from '../../api/client.js'
import { buildQuery } from './filters.js'

export default function useThreads() {
  const [data, setDataState] = useState({ items: [], total: 0, total_pages: 0, page_size: 50 })
  const dataRef = useRef(data)
  const recommendationsRef = useRef(new Map())
  const currentRecommendationRef = useRef(null)
  // Keep local marks/removals in the saved batch as well as the visible list.
  const setData = useCallback(update => {
    const next = typeof update === 'function' ? update(dataRef.current) : update
    dataRef.current = next
    if (currentRecommendationRef.current !== null) {
      recommendationsRef.current.set(currentRecommendationRef.current, next)
    }
    setDataState(next)
  }, [])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const requestIdRef = useRef(0)
  const controllerRef = useRef(null)
  useEffect(() => () => controllerRef.current?.abort(), [])
  const loadThreads = useCallback(async (filters, page, { refresh = false } = {}) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const requestId = ++requestIdRef.current
    const query = buildQuery(filters, page)
    const recommendationKey = filters.view_mode === 'recommend' ? query : null
    if (refresh) recommendationsRef.current.clear()
    setLoadError('')
    if (recommendationKey !== null && recommendationsRef.current.has(recommendationKey)) {
      currentRecommendationRef.current = recommendationKey
      setData(recommendationsRef.current.get(recommendationKey))
      setLoading(false)
      return true
    }
    setLoading(true)
    try {
      const payload = await requestJson(`/api/threads?${query}`, { signal: controller.signal })
      if (requestId !== requestIdRef.current) return false
      currentRecommendationRef.current = recommendationKey
      setData(payload)
      return true
    } catch (error) {
      if (requestId === requestIdRef.current && error.name !== 'AbortError') {
        setLoadError(error.message)
        currentRecommendationRef.current = null
        setData(current => ({ ...current, items: [], total: 0, total_pages: 0 }))
      }
      return false
    } finally {
      if (requestId === requestIdRef.current && !controller.signal.aborted) setLoading(false)
    }
  }, [setData])
  return { data, setData, loading, loadError, loadThreads, requestIdRef }
}
