import { siteUrl } from './api/site.js'
import { LikeOutlined } from '@ant-design/icons'

export const SORT_OPTIONS = [
  { label: '回复', value: 'reply_count' },
  { label: '浏览', value: 'view_count' },
  { label: '参与人数', value: 'participant_count' },
  { label: '金钱 / 购买（旧指标）', value: 'money' },
  { label: '金钱（新采集）', value: 'reward_money' },
  { label: '购买人数（新采集）', value: 'purchase_count' },
  { label: '评分', value: 'rating' },
  { label: '发帖时间', value: 'posted_at' },
]

export const ORDER_OPTIONS = [
  { label: '降序', value: 'desc' },
  { label: '升序', value: 'asc' },
]

export const PAGE_SIZE_OPTIONS = [
  { label: '50 / 页', value: 50 },
  { label: '100 / 页', value: 100 },
  { label: '200 / 页', value: 200 },
]

export const RECOMMEND_PERCENT_OPTIONS = [1, 5, 10, 20, 30, 50, 60].map((value) => ({
  label: `前 ${value}%`,
  value,
}))

export const COMMENT_PAGE_SIZE_OPTIONS = [
  { label: '50 / 页', value: 50 },
  { label: '100 / 页', value: 100 },
  { label: '200 / 页', value: 200 },
  { label: '500 / 页', value: 500 },
]

export const FEEDBACK_OPTIONS = [
  { label: '感兴趣', value: 'like', icon: <LikeOutlined /> },
  { label: '不感兴趣', value: 'dislike' },
]

export function buildWordsQuery(filters, refresh = false) {
  const params = new URLSearchParams()
  params.set('page', String(filters.page || 1))
  params.set('page_size', String(filters.page_size || 50))
  params.set('min_count', String(filters.min_count || 1))
  if (refresh) {
    params.set('refresh', '1')
  }
  if (filters.fid?.trim()) {
    params.set('fid', filters.fid.trim())
  }
  if (filters.q?.trim()) {
    params.set('q', filters.q.trim())
  }
  return params.toString()
}

export function parseWordsUrlState() {
  const params = new URLSearchParams(window.location.search)
  return {
    q: params.get('word_q') || '',
    fid: params.get('word_fid') || '',
    min_count: params.has('min_count') ? Number(params.get('min_count')) || 2 : 2,
    page: params.has('word_page') ? Number(params.get('word_page')) || 1 : 1,
    page_size: params.has('word_page_size') ? Number(params.get('word_page_size')) || 50 : 50,
  }
}

export function writeWordsUrlState(filters, replace = false) {
  const params = new URLSearchParams()
  if (filters.q?.trim()) {
    params.set('word_q', filters.q.trim())
  }
  if (filters.fid?.trim()) {
    params.set('word_fid', filters.fid.trim())
  }
  if (filters.min_count && filters.min_count !== 2) {
    params.set('min_count', String(filters.min_count))
  }
  if (filters.page && filters.page !== 1) {
    params.set('word_page', String(filters.page))
  }
  if (filters.page_size && filters.page_size !== 50) {
    params.set('word_page_size', String(filters.page_size))
  }
  const query = params.toString()
  const nextUrl = query ? `/words?${query}` : '/words'
  window.history[replace ? 'replaceState' : 'pushState']({}, '', siteUrl(nextUrl))
}

export function formatNumber(value) {
  return Number(value || 0).toLocaleString('zh-CN')
}

export function feedbackLabel(value) {
  return FEEDBACK_OPTIONS.find((item) => item.value === value)?.label || ''
}

export function splitKeywords(value) {
  return String(value || '')
    .split(/[\s,，、；;]+/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
}

export function parseThreadTidFromPath() {
  const match = window.location.pathname.match(/^\/thread\/([^/?#]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

export function isWordsPath() {
  return window.location.pathname === '/words'
}
