import { siteId, siteUrl } from '../../api/site.js'
import dayjs from 'dayjs'

export const MAX_HOT_PERIOD = 1000
export const HOT_DAY_VALUES = [3, 5, 7, 14]

export const DEFAULT_FILTERS = {
  q: '',
  exclude_q: '',
  fid: '',
  author_id: '',
  author_name: '',
  dateRange: null,
  sort: 'reply_count',
  order: 'desc',
  page_size: 50,
  view_mode: 'recommend',
  hot_days: 14,
  hot_period: 0,
  hot_anchor: '',
  recommend_top_percent: 50,
  show_disliked: false,
  hide_seen: false,
  only_liked: false,
}

export function normalizeHotDays(value, fallback = DEFAULT_FILTERS.hot_days) {
  const days = Number(value)
  return Number.isInteger(days) && days >= 1 && days <= 365 ? days : fallback
}

export function normalizeHotPeriod(value) {
  const period = Number(value)
  return Number.isInteger(period) && period >= 0 && period <= MAX_HOT_PERIOD ? period : 0
}

export function normalizeHotAnchor(value) {
  return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && dayjs(value).isValid() && dayjs(value).format('YYYY-MM-DD') === value ? value : ''
}

export function hotPeriodRange(filters, today = dayjs()) {
  const days = normalizeHotDays(filters.hot_days)
  const period = normalizeHotPeriod(filters.hot_period)
  const anchor = normalizeHotAnchor(filters.hot_anchor)
  const end = (anchor ? dayjs(anchor) : dayjs(today)).startOf('day').subtract(period * days, 'day')
  return { from: end.subtract(days - 1, 'day').format('YYYY-MM-DD'), to: end.format('YYYY-MM-DD'), anchor: (anchor ? dayjs(anchor) : dayjs(today)).format('YYYY-MM-DD') }
}

const THREAD_FILTER_STORAGE_KEY = 'forum-browser.thread-filters.v1' + (siteId === 'default' ? '' : '.' + siteId)
const FILTER_URL_KEYS = [
  'q', 'exclude_q', 'fid', 'author_id', 'author_name', 'posted_date_from', 'posted_date_to', 'sort', 'order',
  'page_size', 'view', 'hot_days', 'hot_period', 'hot_anchor', 'recommend', 'recommend_top_percent', 'show_disliked', 'hide_seen', 'only_liked',
]

function readPersistedThreadFilters() {
  try {
    const saved = JSON.parse(window.localStorage.getItem(THREAD_FILTER_STORAGE_KEY) || 'null')
    if (!saved || typeof saved !== 'object') return DEFAULT_FILTERS
    const dateRange = Array.isArray(saved.dateRange)
      ? [saved.dateRange[0] ? dayjs(saved.dateRange[0]) : null, saved.dateRange[1] ? dayjs(saved.dateRange[1]) : null]
      : null
    const legacyViewMode = saved.recommend === false ? 'all' : 'recommend'
    const savedFilters = { ...saved }
    delete savedFilters.recommend
    return {
      ...DEFAULT_FILTERS,
      ...savedFilters,
      view_mode: ['recommend', 'hot', 'all'].includes(saved.view_mode) ? saved.view_mode : legacyViewMode,
      hot_days: normalizeHotDays(saved.hot_days),
      hot_period: normalizeHotPeriod(saved.hot_period),
      hot_anchor: normalizeHotAnchor(saved.hot_anchor),
      dateRange,
    }
  } catch {
    return DEFAULT_FILTERS
  }
}

export function persistThreadFilters(filters) {
  try {
    window.localStorage.setItem(THREAD_FILTER_STORAGE_KEY, JSON.stringify({
      ...filters,
      dateRange: filters.dateRange
        ? [filters.dateRange[0]?.format('YYYY-MM-DD') || null, filters.dateRange[1]?.format('YYYY-MM-DD') || null]
        : null,
    }))
  } catch {
    // Local storage can be unavailable in private or restricted browser contexts.
  }
}

export function parseUrlState() {
  const params = new URLSearchParams(window.location.search)
  const baseFilters = FILTER_URL_KEYS.some((key) => params.has(key))
    ? DEFAULT_FILTERS
    : readPersistedThreadFilters()
  const postedDateFrom = params.get('posted_date_from')
  const postedDateTo = params.get('posted_date_to')
  const legacyRecommend = params.has('recommend') ? params.get('recommend') === '1' : null
  const requestedViewMode = params.get('view')
  const viewMode = ['recommend', 'hot', 'all'].includes(requestedViewMode)
    ? requestedViewMode
    : legacyRecommend === null ? baseFilters.view_mode : legacyRecommend ? 'recommend' : 'all'
  return {
    filters: {
      ...baseFilters,
      q: params.has('q') ? params.get('q') || '' : baseFilters.q,
      exclude_q: params.has('exclude_q') ? params.get('exclude_q') || '' : baseFilters.exclude_q,
      fid: params.has('fid') ? params.get('fid') || '' : baseFilters.fid,
      author_id: params.has('author_id') ? params.get('author_id') || '' : baseFilters.author_id,
      author_name: params.has('author_name') ? params.get('author_name') || '' : baseFilters.author_name,
      sort: params.get('sort') || baseFilters.sort,
      order: params.get('order') || baseFilters.order,
      page_size: params.has('page_size') ? Number(params.get('page_size')) : baseFilters.page_size,
      view_mode: viewMode,
      hot_days: params.has('hot_days')
        ? normalizeHotDays(params.get('hot_days'), baseFilters.hot_days)
        : baseFilters.hot_days,
      hot_period: params.has('hot_period') ? normalizeHotPeriod(params.get('hot_period')) : baseFilters.hot_period,
      hot_anchor: params.has('hot_anchor') ? normalizeHotAnchor(params.get('hot_anchor')) : baseFilters.hot_anchor,
      recommend_top_percent: params.has('recommend_top_percent')
        ? Number(params.get('recommend_top_percent')) || baseFilters.recommend_top_percent
        : baseFilters.recommend_top_percent,
      show_disliked: params.has('show_disliked') ? params.get('show_disliked') === '1' : baseFilters.show_disliked,
      hide_seen: params.has('hide_seen') ? params.get('hide_seen') === '1' : baseFilters.hide_seen,
      only_liked: params.has('only_liked') ? params.get('only_liked') === '1' : baseFilters.only_liked,
      dateRange: postedDateFrom || postedDateTo
        ? [
            postedDateFrom ? dayjs(postedDateFrom) : null,
            postedDateTo ? dayjs(postedDateTo) : null,
          ]
        : baseFilters.dateRange,
    },
    page: params.has('page') ? Number(params.get('page')) || 1 : 1,
  }
}

export function writeUrlState(filters, page, replace = false) {
  const params = new URLSearchParams()
  params.set('page', String(page))

  for (const [key, value] of Object.entries(filters)) {
    if (key === 'dateRange') {
      if (value?.[0]) {
        params.set('posted_date_from', value[0].format('YYYY-MM-DD'))
      }
      if (value?.[1]) {
        params.set('posted_date_to', value[1].format('YYYY-MM-DD'))
      }
      continue
    }
    if (key === 'view_mode') {
      params.set('view', value)
      continue
    }
    if (
      value === null ||
      value === undefined ||
      value === '' ||
      value === DEFAULT_FILTERS[key]
    ) {
      continue
    }
    params.set(key, typeof value === 'boolean' ? (value ? '1' : '0') : String(value))
  }

  const query = params.toString()
  const nextUrl = query ? `/?${query}` : '/'
  const method = replace ? 'replaceState' : 'pushState'
  window.history[method]({}, '', siteUrl(nextUrl))
}

export function buildQuery(filters, page) {
  const params = new URLSearchParams()
  params.set('page', String(page))
  params.set('page_size', String(filters.page_size || 50))
  const isHot = filters.view_mode === 'hot'
  params.set('sort', isHot ? 'reply_count' : filters.sort || 'reply_count')
  params.set('order', isHot ? 'desc' : filters.order || 'desc')

  if (filters.q?.trim()) {
    params.set('q', filters.q.trim())
  }
  if (filters.exclude_q?.trim()) {
    params.set('exclude_q', filters.exclude_q.trim())
  }
  if (filters.fid?.trim()) {
    params.set('fid', filters.fid.trim())
  }
  if (filters.author_id?.trim()) {
    params.set('author_id', filters.author_id.trim())
  }
  if (isHot) {
    const range = hotPeriodRange(filters)
    params.set('posted_date_from', range.from)
    params.set('posted_date_to', range.to)
  } else if (filters.view_mode === 'all' && filters.dateRange?.[0]) {
    params.set('posted_date_from', filters.dateRange[0].format('YYYY-MM-DD'))
    if (filters.dateRange?.[1]) {
      params.set('posted_date_to', filters.dateRange[1].format('YYYY-MM-DD'))
    }
  } else if (filters.view_mode === 'all' && filters.dateRange?.[1]) {
    params.set('posted_date_to', filters.dateRange[1].format('YYYY-MM-DD'))
  }
  if (filters.show_disliked) {
    params.set('show_disliked', '1')
  }
  if (filters.view_mode === 'recommend') {
    params.set('recommend', '1')
    params.set('recommend_top_percent', String(filters.recommend_top_percent || 50))
  }
  if (filters.hide_seen) {
    params.set('hide_seen', '1')
  }
  if (filters.only_liked) {
    params.set('only_liked', '1')
  }
  return params.toString()
}
