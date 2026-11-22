import { useCallback, useEffect, useRef, useState } from 'react'
import { DEFAULT_FILTERS, parseUrlState, persistThreadFilters, writeUrlState } from './filters.js'

export default function useThreadFilters({ active, form, loadThreads, hasItems }) {
  const [state, setState] = useState(parseUrlState)
  const initialized = useRef(false)
  const { filters, page } = state

  const applyFilters = useCallback((nextFilters, nextPage = 1, replace = false, options) => {
    initialized.current = true
    form.setFieldsValue(nextFilters)
    setState({ filters: nextFilters, page: nextPage })
    persistThreadFilters(nextFilters)
    writeUrlState(nextFilters, nextPage, replace)
    return loadThreads(nextFilters, nextPage, options)
  }, [form, loadThreads])

  useEffect(() => {
    if (!active || initialized.current) return
    const initial = parseUrlState()
    form.setFieldsValue(initial.filters)
    writeUrlState(initial.filters, initial.page, true)
    loadThreads(initial.filters, initial.page).then(success => {
      if (!success) return
      initialized.current = true
      persistThreadFilters(initial.filters)
      setState(initial)
    })
  }, [active, form, loadThreads])

  useEffect(() => {
    const restore = () => {
      if (window.location.pathname !== '/') return
      const next = parseUrlState()
      form.setFieldsValue(next.filters)
      setState(next)
      persistThreadFilters(next.filters)
      if (hasItems && next.page === page && JSON.stringify(next.filters) === JSON.stringify(filters)) return
      initialized.current = true
      loadThreads(next.filters, next.page)
    }
    window.addEventListener('popstate', restore)
    return () => window.removeEventListener('popstate', restore)
  }, [filters, page, hasItems, form, loadThreads])

  const searchKeyword = useCallback(keyword => {
    if (keyword) applyFilters({ ...DEFAULT_FILTERS, q: keyword, view_mode: 'recommend' })
  }, [applyFilters])

  return { filters, page, applyFilters, searchKeyword }
}
