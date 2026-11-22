import { siteUrl } from './api/site.js'
import { lazy, Suspense, useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ConfigProvider, theme } from 'antd'
import { useControls } from './useControls.js'
import zhCN from 'antd/locale/zh_CN'
import './App.css'
import './Reader.css'
import ThreadListPage from './pages/ThreadListPage.jsx'
import { isWordsPath, parseThreadTidFromPath, parseWordsUrlState, writeWordsUrlState } from './shared.jsx'
import { DEFAULT_FILTERS, writeUrlState } from './features/threads/filters.js'
import { insightsUrl } from './features/threads/insightState.js'
import { postJson, requestJson } from './api/client.js'
import { prefersDark, ThemeContext, themeStorageKey } from './appearance.js'
import useViewportInsets from './useViewportInsets.js'

const ThreadDetailPage = lazy(() => import('./pages/ThreadDetailPage.jsx'))
const WordsPage = lazy(() => import('./pages/WordsPage.jsx'))
const CrawlAdminPage = lazy(() => import('./pages/CrawlAdminPage.jsx'))
const InsightsPage = lazy(() => import('./pages/InsightsPage.jsx'))
const RankingsPage = lazy(() => import('./pages/RankingsPage.jsx'))

const appTheme = {
  token: {
    borderRadius: 8,
    colorPrimary: '#3159a7',
    colorText: '#182230',
    colorTextSecondary: '#5e6b7b',
    colorTextPlaceholder: '#5e6b7b',
    colorBorder: '#dfe5ec',
    colorBgLayout: '#f4f6f8',
    controlHeight: 40,
    controlHeightSM: 32,
    controlHeightLG: 44,
    fontWeightStrong: 600,
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif',
  },
  components: {
    Button: {
      primaryShadow: 'none',
      defaultShadow: 'none',
    },
    Table: {
      cellPaddingBlock: 16,
      headerBg: '#f8fafc',
      headerColor: '#667085',
    },
  },
}

const darkTheme = {
  algorithm: theme.darkAlgorithm,
  token: {
    ...appTheme.token,
    colorPrimary: '#4370bd',
    colorPrimaryText: '#a8c6ff',
    colorLink: '#a8c6ff',
    colorLinkHover: '#c4d8ff',
    colorText: '#e4ebf5',
    colorTextSecondary: '#afbdd0',
    colorTextPlaceholder: '#8b9bb1',
    colorBorder: '#39495e',
    colorBorderSecondary: '#2b394d',
    colorBgLayout: '#101722',
    colorBgContainer: '#182232',
    colorBgElevated: '#202d40',
  },
  components: {
    ...appTheme.components,
    Table: { ...appTheme.components.Table, headerBg: '#202d40', headerColor: '#afbdd0' },
  },
}

function getRoute() {
  return {
    detailTid: parseThreadTidFromPath(),
    wordsOpen: isWordsPath(),
    adminOpen: window.location.pathname === '/admin',
    insightsOpen: window.location.pathname === '/insights',
    rankingsOpen: window.location.pathname === '/rankings',
    location: `${window.location.pathname}${window.location.search}`,
  }
}

function App() {
  const { message } = useControls()
  useViewportInsets()
  const [touchInput, setTouchInput] = useState(() => window.matchMedia('(hover: none)').matches)
  useEffect(() => {
    const query = window.matchMedia('(hover: none)')
    const update = () => setTouchInput(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  const [dark, setDark] = useState(prefersDark)
  const currentTheme = dark ? darkTheme : appTheme
  const [route, setRoute] = useState(getRoute)
  const [forums, setForums] = useState([])
  const threadListActive = !route.detailTid && !route.wordsOpen && !route.adminOpen && !route.insightsOpen && !route.rankingsOpen
  const needsForums = threadListActive || route.insightsOpen
  const [seenTids, setSeenTids] = useState({})
  const listUrlRef = useRef(window.location.pathname === '/' ? `/${window.location.search}` : '/')
  const listScrollRef = useRef(0)
  const keywordSearchRef = useRef(null)
  const registerKeywordSearch = useCallback((handler) => { keywordSearchRef.current = handler }, [])

  useEffect(() => {
    if (!needsForums) return
    const controller = new AbortController()
    requestJson('/api/forums', { signal: controller.signal })
      .then(payload => {
        if (!controller.signal.aborted) setForums(payload.items)
      })
      .catch(() => { /* Retain the last loaded options if the server is unavailable. */ })
    return () => controller.abort()
  }, [needsForums])

  const toggle = useCallback(() => setDark(value => !value), [])
  useLayoutEffect(() => {
    const mode = dark ? 'dark' : 'light'
    document.documentElement.dataset.theme = mode
    try {
      localStorage.setItem(themeStorageKey, mode)
    } catch {
      // The toggle still works when browser storage is unavailable.
    }
    ConfigProvider.config({
      holderRender: children => <ConfigProvider locale={zhCN} theme={currentTheme} wave={{ disabled: touchInput }}>{children}</ConfigProvider>,
    })
  }, [currentTheme, dark, touchInput])

  useEffect(() => {
    const handlePopState = () => {
      const nextRoute = getRoute()
      setRoute(nextRoute)
      if (!nextRoute.detailTid && !nextRoute.wordsOpen && !nextRoute.adminOpen && !nextRoute.insightsOpen && !nextRoute.rankingsOpen) {
        const savedScroll = window.history.state?.pageScroll ?? window.history.state?.insightScroll
        window.requestAnimationFrame(() => window.scrollTo({ top: Number.isFinite(savedScroll) ? savedScroll : listScrollRef.current }))
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  const markSeen = useCallback(async tid => {
    try {
      await postJson('/api/seen', { tid, seen: 1 })
      setSeenTids(current => ({ ...current, [tid]: true }))
      return true
    } catch (error) {
      message.error(error.message || '保存已看失败')
      return false
    }
  }, [message])

  const openInsights = useCallback((filters, tab = 'missed') => {
    listUrlRef.current = `${window.location.pathname}${window.location.search}`
    listScrollRef.current = window.scrollY
    window.history.replaceState({ ...window.history.state, pageScroll: window.scrollY }, '', window.location.href)
    window.history.pushState({ fromThreadList: true, listUrl: listUrlRef.current, listScroll: listScrollRef.current }, '', siteUrl(insightsUrl(filters, tab)))
    setRoute(getRoute())
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [])

  const navigateInsights = useCallback((url, { replace = false, fromInsights = false, preserveScroll = false } = {}) => {
    const current = window.history.state || {}
    if (!replace) window.history.replaceState({ ...current, pageScroll: window.scrollY }, '', window.location.href)
    const next = { fromThreadList: current.fromThreadList, listUrl: current.listUrl, listScroll: current.listScroll, fromInsights, pageScroll: preserveScroll ? window.scrollY : 0 }
    window.history[replace ? 'replaceState' : 'pushState'](next, '', siteUrl(url))
    setRoute(getRoute())
  }, [])

  const openThreadDetail = useCallback((tid) => {
    const nextTid = String(tid)
    listUrlRef.current = `${window.location.pathname}${window.location.search}`
    listScrollRef.current = window.scrollY
    window.history.pushState({ fromThreadList: true, listUrl: listUrlRef.current, listScroll: listScrollRef.current }, '', siteUrl(`/thread/${encodeURIComponent(nextTid)}`))
    setRoute(getRoute())
    window.scrollTo({ top: 0 })
  }, [])

  const closeThreadDetail = useCallback(() => {
    if (window.history.state?.fromThreadList) {
      listUrlRef.current = window.history.state.listUrl || '/'
      listScrollRef.current = window.history.state.listScroll || 0
      window.history.back()
      return
    }
    window.history.replaceState({}, '', siteUrl(listUrlRef.current || '/'))
    setRoute(getRoute())
    window.requestAnimationFrame(() => window.scrollTo({ top: listScrollRef.current }))
  }, [])

  const openWordsPage = useCallback(() => {
    listUrlRef.current = `${window.location.pathname}${window.location.search}`
    listScrollRef.current = window.scrollY
    writeWordsUrlState(parseWordsUrlState())
    setRoute(getRoute())
    window.scrollTo({ top: 0 })
  }, [])

  const openAdminPage = useCallback(() => {
    listUrlRef.current = `${window.location.pathname}${window.location.search}`
    listScrollRef.current = window.scrollY
    window.history.pushState({}, '', siteUrl('/admin'))
    setRoute(getRoute())
    window.scrollTo({ top: 0 })
  }, [])

  const openRankingsPage = useCallback((event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    listUrlRef.current = `${window.location.pathname}${window.location.search}`
    listScrollRef.current = window.scrollY
    window.history.replaceState({ ...window.history.state, pageScroll: window.scrollY }, '', window.location.href)
    window.history.pushState({ fromThreadList: true, listUrl: listUrlRef.current, listScroll: listScrollRef.current }, '', siteUrl('/rankings'))
    setRoute(getRoute())
    window.scrollTo({ top: 0 })
  }, [])

  const navigateRankings = useCallback((query) => {
    window.history.replaceState(window.history.state, '', siteUrl(`/rankings?${query}`))
    setRoute(getRoute())
  }, [])

  const closeWordsPage = useCallback((keyword = '') => {
    if (keyword) {
      const nextFilters = { ...DEFAULT_FILTERS, q: keyword, view_mode: 'recommend' }
      writeUrlState(nextFilters, 1)
      keywordSearchRef.current?.(keyword)
      setRoute(getRoute())
      return
    }
    window.history.replaceState({}, '', siteUrl(listUrlRef.current || '/'))
    setRoute(getRoute())
    window.requestAnimationFrame(() => window.scrollTo({ top: listScrollRef.current }))
  }, [])

  return (
    <ConfigProvider locale={zhCN} theme={currentTheme} button={{ autoInsertSpace: false }} wave={{ disabled: touchInput }}>
      <ThemeContext value={{ dark, toggle }}>
      <ThreadListPage
        active={threadListActive}
        forums={forums}
        onOpenThread={openThreadDetail}
        onOpenWords={openWordsPage}
        onOpenAdmin={openAdminPage}
        onKeywordSearchReady={registerKeywordSearch}
        onOpenInsights={openInsights}
        onOpenRankings={openRankingsPage}
        onSeen={markSeen}
        seenTids={seenTids}
      />
      <Suspense fallback={<main className="app-shell" role="status">正在加载页面…</main>}>
      {route.detailTid && <ThreadDetailPage key={route.detailTid} tid={route.detailTid} onBack={closeThreadDetail} />}
      {route.wordsOpen && <WordsPage onBackToThreads={closeWordsPage} />}
      {route.adminOpen && <CrawlAdminPage onBack={closeThreadDetail} />}
      {route.insightsOpen && <InsightsPage location={route.location} onBack={closeThreadDetail} onNavigate={navigateInsights} onSeen={markSeen} seenTids={seenTids} forums={forums} />}
      {route.rankingsOpen && <RankingsPage location={route.location} onBack={closeThreadDetail} onNavigate={navigateRankings} />}
      </Suspense>
      </ThemeContext>
    </ConfigProvider>
  )
}

export default App
