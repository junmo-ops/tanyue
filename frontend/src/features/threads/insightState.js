import { DEFAULT_FILTERS, hotPeriodRange, normalizeHotAnchor, normalizeHotDays, normalizeHotPeriod } from './filters.js'

export const INSIGHT_TABS = [
  ['missed', '漏看精选'], ['growth', '热度增长'], ['overview', '概览'],
  ['authors', '作者发现'], ['topics', '话题变化'],
]

export function insightsUrl(filters, tab = 'missed') {
  const range = hotPeriodRange(filters)
  const params = new URLSearchParams({
    days: normalizeHotDays(filters.hot_days), period: normalizeHotPeriod(filters.hot_period),
    anchor: range.anchor, fid: filters.fid || '', tab,
  })
  return `/insights?${params}`
}

export function parseInsightsState(location = window.location.href) {
  const params = new URL(location, window.location.origin).searchParams
  const filters = {
    hot_days: normalizeHotDays(params.get('days'), DEFAULT_FILTERS.hot_days),
    hot_period: normalizeHotPeriod(params.get('period')),
    hot_anchor: normalizeHotAnchor(params.get('anchor')),
    fid: params.get('fid') || '',
  }
  const range = hotPeriodRange(filters)
  const tab = INSIGHT_TABS.some(([value]) => value === params.get('tab')) ? params.get('tab') : 'missed'
  return {
    filters, tab,
    page: Math.min(10000, Math.max(1, Number.parseInt(params.get('page'), 10) || 1)),
    selection: params.get('focus') === 'posts' ? {
      dateFrom: normalizeHotAnchor(params.get('from')) || range.from,
      dateTo: normalizeHotAnchor(params.get('to')) || range.to,
      fid: params.get('result_fid') ?? filters.fid,
      q: params.get('q') || '', authorId: params.get('author_id') || '',
      authorName: params.get('author_name') || '', hideSeen: params.get('unseen') === '1',
    } : null,
  }
}

export function insightResultsUrl(filters, tab, selection, page = 1) {
  const url = new URL(insightsUrl(filters, tab), window.location.origin)
  const range = hotPeriodRange(filters)
  const values = {
    focus: 'posts', from: selection.dateFrom || range.from, to: selection.dateTo || range.to,
    result_fid: selection.fid ?? filters.fid, q: selection.q || '',
    author_id: selection.authorId || '', author_name: selection.authorName || '',
    unseen: selection.hideSeen ? '1' : '0', page,
  }
  for (const [key, value] of Object.entries(values)) url.searchParams.set(key, value)
  return `${url.pathname}${url.search}`
}
