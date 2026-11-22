import MobileSheet from '../MobileSheet.jsx'
import { siteFetch, siteUrl } from '../api/site.js'
import SiteMenu from '../SiteMenu.jsx'
import { useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { Grid, Table } from 'antd'
import { useControls } from '../useControls.js'
import { BarChartOutlined, DownOutlined, SearchOutlined, FireOutlined, MessageOutlined, MoreOutlined, SyncOutlined, TagsOutlined, TrophyOutlined } from '@ant-design/icons'
import useThreadFilters from '../features/threads/useThreadFilters.js'
import useThreads from '../features/threads/useThreads.js'
import ThreadFilters from '../features/threads/ThreadFilters.jsx'
import useThreadColumns from '../features/threads/useThreadColumns.jsx'
import { FEEDBACK_OPTIONS, feedbackLabel, formatNumber, ORDER_OPTIONS, SORT_OPTIONS } from '../shared.jsx'
import { DEFAULT_FILTERS, hotPeriodRange, MAX_HOT_PERIOD } from '../features/threads/filters.js'
import InsightsPreview from '../features/threads/InsightsPreview.jsx'
import { ThemeContext } from '../appearance.js'
import ThemeToggle from '../ThemeToggle.jsx'

const { useBreakpoint } = Grid



function formatStatusTime(value) {
  if (!value) return '未记录同步'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}

export default function ThreadListPage({ active, onOpenThread, onOpenWords, onOpenAdmin, onKeywordSearchReady, onOpenInsights, onOpenRankings, onSeen: markSeen, seenTids, forums }) {
  const { Button, Checkbox, Empty, Form, Pagination, Skeleton, Space, Spin, Switch, Tag, message, Typography } = useControls()
  const { dark, toggle } = useContext(ThemeContext)
  const { Text, Title } = Typography
  const [form] = Form.useForm()
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const { data: rawData, setData, loading, loadError, loadThreads, requestIdRef } = useThreads()
  const data = useMemo(() => ({ ...rawData, items: rawData.items.map(item => seenTids[item.tid] ? { ...item, seen: 1 } : item) }), [rawData, seenTids])
  const { filters, page, applyFilters, searchKeyword: handleWordSearch } = useThreadFilters({ active, form, loadThreads, hasItems: data.items.length > 0 })
  const [dataStatus, setDataStatus] = useState(null)
  const [insightsRevision, setInsightsRevision] = useState(0)
  const [feedbackSavingTid, setFeedbackSavingTid] = useState('')
  const [commentFetchSavingTid, setCommentFetchSavingTid] = useState('')
  const forumOptions = useMemo(() => [
    { label: '全部', value: '' },
    ...forums.map(item => ({ label: `${item.forum_name} (${item.thread_count})`, value: item.fid })),
  ], [forums])
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [menuOpen, setMenuOpen] = useState(false)
  const listItems = isMobile && filters.hide_seen
    ? data.items.filter(thread => !Number(thread.seen))
    : data.items
  const [advancedFiltersOpen, setAdvancedFiltersOpen] = useState(false)
  const [showActions, setShowActions] = useState(true)
  const [mobileActionTid, setMobileActionTid] = useState('')
  const showInsightsPreview = !isMobile && filters.view_mode === 'hot' && !(
    filters.q?.trim() || filters.exclude_q?.trim() || filters.author_id ||
    filters.hide_seen || filters.only_liked || filters.show_disliked
  )
  const mobileActionThread = useMemo(
    () => data.items.find((item) => item.tid === mobileActionTid) || null,
    [data.items, mobileActionTid],
  )

  useEffect(() => {
    onKeywordSearchReady(handleWordSearch)
    return () => onKeywordSearchReady(null)
  }, [handleWordSearch, onKeywordSearchReady])

  useEffect(() => {
    async function loadStatus() {
      try {
        const response = await siteFetch('/api/status')
        const payload = await response.json()
        if (response.ok) setDataStatus(payload)
      } catch {
        setDataStatus(null)
      }
    }
    if (active) loadStatus()
  }, [active])

  const handleFeedback = useCallback(async (tid, feedback, currentFeedback) => {
    const nextFeedback = currentFeedback === feedback ? '' : feedback
    const originalItem = data.items.find((item) => item.tid === tid)
    const originalIndex = data.items.findIndex((item) => item.tid === tid)
    const requestId = requestIdRef.current
    setFeedbackSavingTid(tid)
    try {
      const response = await siteFetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tid, feedback: nextFeedback }),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.error || '保存标记失败')
      }
      const savedFeedback = payload.feedback
      setInsightsRevision(value => value + 1)
      const shouldHide = savedFeedback === 'dislike' && !filters.show_disliked
      if (requestIdRef.current === requestId) setData((current) => ({
        ...current,
        total: shouldHide && current.items.some((item) => item.tid === tid) ? Math.max(0, current.total - 1) : current.total,
        items: shouldHide ? current.items.filter((item) => item.tid !== tid) : current.items.map((item) => (
          item.tid === tid ? { ...item, feedback: savedFeedback } : item
        )),
      }))
      if (shouldHide && originalItem) {
        let undoPending = false
        const key = `undo-${tid}`
        message.success({ key, duration: 8, content: <span>已收起不感兴趣的帖子 <Button type="link" size="small" onClick={async () => {
          if (undoPending) return
          undoPending = true
          try {
            const response = await siteFetch('/api/feedback', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tid, feedback: currentFeedback || '' }) })
            if (!response.ok) throw new Error('撤销失败，请重试')
            setInsightsRevision(value => value + 1)
            if (requestIdRef.current === requestId) {
              setData((current) => {
                if (current.items.some((item) => item.tid === tid)) return current
                const items = [...current.items]
                items.splice(originalIndex, 0, originalItem)
                return { ...current, items, total: current.total + 1 }
              })
            }
            message.success({ key, content: '已撤销，下次查询也会恢复显示' })
          } catch (error) {
            undoPending = false
            message.error(error.message)
          }
        }}>撤销</Button></span> })
      } else {
        message.success(savedFeedback ? `已标记为${feedbackLabel(savedFeedback)}` : '已取消标记')
      }
    } catch (error) {
      message.error(error.message)
    } finally {
      setFeedbackSavingTid('')
    }
  }, [Button, message, data.items, filters.show_disliked, requestIdRef, setData])

  const handleCommentFetch = useCallback(async (tid, checked) => {
    setCommentFetchSavingTid(tid)
    try {
      const response = await siteFetch('/api/comment-fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tid, fetch_comments: checked ? 1 : 0 }),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload.error || '保存评论开关失败')
      }
      setData((current) => ({
        ...current,
        items: current.items.map((item) => (
          item.tid === tid ? { ...item, fetch_comments: payload.fetch_comments } : item
        )),
      }))
    } catch (error) {
      message.error(error.message)
    } finally {
      setCommentFetchSavingTid('')
    }
  }, [message, setData])


  const openThreadAndMarkSeen = useCallback((tid) => {
    markSeen(tid)
    onOpenThread(tid)
  }, [markSeen, onOpenThread])

  async function readMobileThread(event, tid) {
    const row = event.currentTarget.closest('article')
    const next = row?.nextElementSibling
    const top = next?.getBoundingClientRect().top
    const wasScrolled = window.scrollY > 0
    if (await markSeen(tid) && filters.hide_seen && next && wasScrolled) {
      requestAnimationFrame(() => {
        if (next.isConnected && next.getBoundingClientRect().height > 0) {
          window.scrollBy({ top: next.getBoundingClientRect().top - top, behavior: 'instant' })
        }
      })
    }
  }

  const columns = useThreadColumns({ showActions, feedbackSavingTid, handleFeedback, isMobile, compactStats: !screens.xl, markSeen, openThreadAndMarkSeen, setMobileActionTid })

  const handleSearch = (values) => {
    const nextFilters = { ...filters, ...values }
    applyFilters(nextFilters)
    setMobileFiltersOpen(false)
  }

  const handleReset = () => {
    applyFilters({ ...DEFAULT_FILTERS, view_mode: filters.view_mode, hot_days: filters.hot_days })
  }

  const handleTableChange = (pagination) => {
    const nextPage = pagination.current || 1
    applyFilters(filters, nextPage)
  }

  const forumLabel = useCallback((fid) => (
    forumOptions.find((option) => option.value === String(fid || ''))?.label?.replace(/\s*\([^)]*\)$/, '') || fid || '未知板块'
  ), [forumOptions])

  const activeFilterChips = useMemo(() => {
    const chips = []
    if (filters.q?.trim()) chips.push({ key: 'q', label: `包含：${filters.q.trim()}` })
    if (filters.exclude_q?.trim()) chips.push({ key: 'exclude_q', label: `排除：${filters.exclude_q.trim()}` })
    if (filters.fid) chips.push({ key: 'fid', label: forumLabel(filters.fid) })
    if (filters.author_id) chips.push({ key: 'author_id', label: `作者：${filters.author_name || filters.author_id}`, resetKeys: ['author_id', 'author_name'] })
    if (filters.view_mode === 'all' && (filters.dateRange?.[0] || filters.dateRange?.[1])) {
      chips.push({
        key: 'dateRange',
        label: `${filters.dateRange?.[0]?.format('YYYY-MM-DD') || '不限'} 至 ${filters.dateRange?.[1]?.format('YYYY-MM-DD') || '不限'}`,
      })
    }
    if (filters.view_mode === 'all') {
      const sortLabel = SORT_OPTIONS.find((option) => option.value === filters.sort)?.label
      const orderLabel = ORDER_OPTIONS.find((option) => option.value === filters.order)?.label
      chips.push({ key: 'sort', label: `${sortLabel || '排序'} ${orderLabel || ''}`.trim(), resetKeys: ['sort', 'order'] })
    } else if (filters.view_mode === 'hot') {
      chips.push({ key: 'view_mode', label: '按回复数排序' })
    } else {
      chips.push({ key: 'view_mode', label: `随机推荐 · 前 ${filters.recommend_top_percent || 50}%` })
    }
    if (filters.hide_seen && filters.view_mode !== 'hot') chips.push({ key: 'hide_seen', label: '已隐藏看过' })
    if (filters.only_liked) chips.push({ key: 'only_liked', label: '只看感兴趣' })
    if (filters.show_disliked) chips.push({ key: 'show_disliked', label: '显示不感兴趣' })
    return chips
  }, [filters, forumLabel])

  const handleRemoveFilter = (chip) => {
    const nextFilters = { ...filters }
    for (const key of chip.resetKeys || [chip.key]) {
      nextFilters[key] = DEFAULT_FILTERS[key]
    }
    applyFilters(nextFilters)
  }

  const handleShuffle = () => {
    applyFilters(filters, 1, true, { refresh: true })
    window.scrollTo({ top: 0, behavior: 'instant' })
  }

  const handleViewModeChange = (viewMode) => {
    const nextFilters = { ...filters, ...form.getFieldsValue(), view_mode: viewMode }
    applyFilters(nextFilters)
  }

  const handleHotDaysChange = (hotDays) => {
    const nextFilters = { ...filters, ...form.getFieldsValue(), view_mode: 'hot', hot_days: hotDays, hot_period: 0, hot_anchor: '' }
    applyFilters(nextFilters)
  }

  const handleHotPeriodChange = (period, latest = false) => {
    if (period < 0 || period > MAX_HOT_PERIOD) return
    applyFilters({ ...filters, ...form.getFieldsValue(), hot_period: period, hot_anchor: latest ? '' : hotPeriodRange(filters).anchor })
  }

  const handlePageChange = (nextPage) => {
    applyFilters(filters, nextPage)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }


  return (
    <main className="app-shell thread-list-shell thread-feed" hidden={!active}>
      {isMobile ? <header className="compact-reader-header">
        <span className="tanyue-mark" aria-label="坛阅">坛</span><SiteMenu />
        <div className="compact-reader-icons">
          <Button type="text" aria-label="搜索帖子" aria-expanded={searchOpen} icon={<SearchOutlined />} onClick={() => setSearchOpen(!searchOpen)} />
          <Button type="text" aria-label="更多功能" icon={<MoreOutlined />} onClick={() => setMenuOpen(true)} />
        </div>
        <MobileSheet title="更多功能" open={menuOpen} onClose={() => setMenuOpen(false)}>
          <nav className="compact-reader-menu" aria-label="功能导航" onClick={() => setMenuOpen(false)}>
            <Button type="text" href={siteUrl('/rankings')} icon={<TrophyOutlined />} onClick={onOpenRankings}>排行榜</Button>
            <Button type="text" icon={<BarChartOutlined />} onClick={() => onOpenInsights(filters)}>数据分析</Button>
            <Button type="text" icon={<TagsOutlined />} onClick={onOpenWords}>随机发现</Button>
            <Button type="text" icon={<SyncOutlined />} onClick={onOpenAdmin}>采集管理</Button>
          </nav>
          <div className="reader-menu-appearance">
            <span id="reader-menu-theme-label">深色模式</span>
            <Switch aria-labelledby="reader-menu-theme-label" checked={dark} onChange={toggle} />
          </div>
          {dataStatus && <p className="reader-menu-status">已收录 {formatNumber(dataStatus.thread_count)} 篇 · {formatStatusTime(dataStatus.last_sync?.finished_at || dataStatus.database_modified_at)}</p>}
        </MobileSheet>
      </header> : <header className="thread-hero">
        <div className="thread-hero-copy">
          <div className="thread-hero-title">
            <FireOutlined className="header-icon" />
            <Title level={1}>帖子发现</Title>
            <ThemeToggle />
            <SiteMenu />
          </div>
          <Text type="secondary">从本地数据中快速找到值得看的内容</Text>
          {dataStatus && (
            <details className="data-status-disclosure">
              <summary aria-label={`查看数据状态，已收录 ${formatNumber(dataStatus.thread_count)} 篇`}>
                {dataStatus.environment === 'test' && <span className="environment-badge is-test">测试环境</span>}
                <span className="data-status-total">已收录 {formatNumber(dataStatus.thread_count)} 篇</span>
                <span className="data-status-trigger"><span>数据状态</span> <DownOutlined /></span>
              </summary>
            <div className="data-status-line">
              <span className={`environment-badge ${dataStatus.environment === 'test' ? 'is-test' : ''}`}>
                {dataStatus.environment === 'test' ? '测试环境' : '生产环境'}
              </span>
              <span>{dataStatus.database_name}</span>
              <span>{formatNumber(dataStatus.thread_count)} 篇</span>
              <span>
                最后同步：{formatStatusTime(
                  dataStatus.last_sync?.finished_at || dataStatus.last_sync?.started_at || dataStatus.database_modified_at,
                )}
              </span>
            </div>
            </details>
          )}
        </div>
        <nav className="thread-hero-actions" aria-label="功能导航">
          <Button type="text" href={siteUrl('/rankings')} icon={<TrophyOutlined />} onClick={onOpenRankings}>排行榜</Button>
          <Button type="text" icon={<BarChartOutlined />} onClick={() => onOpenInsights(filters)}>数据分析</Button>
          <Button type="text" icon={<TagsOutlined />} onClick={onOpenWords} aria-label="随机发现">随机发现</Button>
          <Button type="text" icon={<SyncOutlined />} onClick={onOpenAdmin}>采集管理</Button>
        </nav>
      </header>}

      <div className="thread-reader-content">
      <ThreadFilters onToggleSeen={() => applyFilters({ ...filters, hide_seen: !filters.hide_seen })} {...{ searchOpen, form, filters, isMobile, forumOptions, loading, showActions, setShowActions, mobileFiltersOpen, setMobileFiltersOpen, advancedFiltersOpen, setAdvancedFiltersOpen, handleSearch, handleViewModeChange, handleHotDaysChange, handleHotPeriodChange, handleShuffle, handleReset }} />

      <div id="period-insights" hidden={!showInsightsPreview}>
        <InsightsPreview filters={filters} isMobile={isMobile} active={active && showInsightsPreview} onOpen={onOpenInsights} onSeen={markSeen} seenTids={seenTids} refreshKey={insightsRevision} />
      </div>

      {(!isMobile || activeFilterChips.some(chip => !['view_mode', 'sort', 'hide_seen'].includes(chip.key))) && <section id="thread-results-start" className="filter-summary" aria-label="当前筛选条件">
        <div className="thread-results-heading">
          <h2>帖子列表</h2><span>{formatNumber(data.total)} 篇</span>
        </div>
        <div className="filter-summary-chips">
          <span className="filter-summary-label">当前条件</span>
          {activeFilterChips.filter(chip => !isMobile || !['view_mode', 'sort', 'hide_seen'].includes(chip.key)).map((chip) => (
            <Tag key={chip.key} closable={chip.key !== 'view_mode'} onClose={(event) => {
              event.preventDefault()
              handleRemoveFilter(chip)
            }}>
              {chip.label}
            </Tag>
          ))}
          {!isMobile && filters.view_mode === 'hot' && (
            <Checkbox
              className="hot-hide-seen-filter"
              checked={filters.hide_seen}
              onChange={(event) => applyFilters({ ...filters, hide_seen: event.target.checked })}
            >
              隐藏已看
            </Checkbox>
          )}
        </div>
      </section>}

      {loadError ? (
        <div className="thread-result-state" role="alert">
          <Text strong>帖子加载失败</Text>
          <p>{loadError}</p>
          <Button loading={loading} onClick={() => loadThreads(filters, page)}>重新加载</Button>
        </div>
      ) : !loading && !listItems.length ? (
        <div className="thread-result-state">
          <Empty description="没有符合条件的帖子" />
          <Space wrap>
            {filters.view_mode === 'hot' && filters.hot_days < 14 && <Button onClick={() => handleHotDaysChange(14)}>扩大到近 14 天</Button>}
            <Button onClick={handleReset}>重置当前模式的筛选</Button>
          </Space>
        </div>
      ) : loading && !data.items.length ? (
        <section className="thread-list-skeleton" role="status" aria-label="正在加载帖子">
          {[0, 1, 2].map(key => <Skeleton key={key} active title={{ width: '70%' }} paragraph={{ rows: 1 }} />)}
        </section>
      ) : isMobile ? (
        <section className="mobile-thread-panel" aria-busy={loading}>
          <Spin spinning={loading}>
            {data.items.length ? (
              <div className="mobile-thread-list">
                {listItems.map((thread) => (
                  <article className={`mobile-thread-item ${Number(thread.seen) === 1 ? 'is-seen' : ''}`} key={thread.tid}>
                    <div className="mobile-thread-main">
                      <a
                        className="mobile-thread-title"
                        href={thread.official_url}
                        target="_blank"
                        rel="noreferrer"
                        title={thread.title}
                        onClick={event => readMobileThread(event, thread.tid)}
                      >
                        {thread.title}
                      </a>
                      <div className="mobile-thread-meta">
                        <span className="mobile-forum-badge">{forumLabel(thread.fid)}</span>
                        <time title={thread.posted_at}>{thread.posted_at?.slice(0, 10) || '-'}</time>
                        {Number(thread.seen) === 1 && <span>已看</span>}
                        <span className="compact-metric">{filters.view_mode === 'all' && filters.sort === 'view_count' ? formatNumber(thread.view_count) + ' 浏览' : formatNumber(thread.reply_count) + ' 回复'}</span>
                      </div>
                    </div>
                    {showActions && (
                      <Button
                        type="text"
                        className="mobile-thread-more"
                        icon={<MoreOutlined />}
                        onClick={() => setMobileActionTid(thread.tid)}
                        aria-label="帖子操作"
                      />
                    )}
                  </article>
                ))}
              </div>
            ) : <Empty description="没有符合条件的帖子" />}
          </Spin>
          {filters.view_mode !== 'recommend' && <Pagination
            simple
            current={page}
            pageSize={data.page_size || filters.page_size}
            total={data.total}
            onChange={handlePageChange}
            className="mobile-thread-pagination"
          />}
        </section>
      ) : (
        <section className="table-panel thread-table-panel">
          <Table
            className={showActions ? 'thread-table has-actions' : 'thread-table no-actions'}
            rowKey="tid"
            loading={loading}
            columns={columns}
            dataSource={data.items}
            size="middle"
            scroll={{ x: screens.xl ? 1080 : 720 }}
            pagination={filters.view_mode === 'recommend' ? false : {
              current: page,
              pageSize: data.page_size || filters.page_size,
              total: data.total,
              showSizeChanger: false,
              showQuickJumper: true,
              showTotal: (total, range) => `${range[0]}-${range[1]} / ${total} 条`,
            }}
            onChange={handleTableChange}
          />
        </section>
      )}
      {filters.view_mode === 'recommend' && !loadError && data.items.length > 0 && (
        <div className="thread-result-state">
          <Button size="large" icon={<SyncOutlined />} loading={loading} onClick={handleShuffle}>再看一批</Button>
        </div>
      )}
      </div>
        <MobileSheet
          title="帖子操作"
          open={isMobile && Boolean(mobileActionThread)}
          onClose={() => setMobileActionTid('')}
          className="mobile-action-drawer"
        >
          {mobileActionThread && (
            <div className="mobile-action-content">
              <p className="mobile-action-title">{mobileActionThread.title}</p>
              <div className="mobile-action-grid">
                <Button
                  icon={<MessageOutlined />}
                  onClick={() => {
                    setMobileActionTid('')
                    openThreadAndMarkSeen(mobileActionThread.tid)
                  }}
                >
                  评论
                </Button>
                {FEEDBACK_OPTIONS.map((option) => (
                  <Button
                    key={option.value}
                    type={mobileActionThread.feedback === option.value ? 'primary' : 'default'}
                    icon={option.icon}
                    loading={feedbackSavingTid === mobileActionThread.tid && mobileActionThread.feedback !== option.value}
                    onClick={() => {
                      setMobileActionTid('')
                      handleFeedback(mobileActionThread.tid, option.value, mobileActionThread.feedback)
                    }}
                  >
                    {option.label}
                  </Button>
                ))}
                <Button
                  type={Number(mobileActionThread.fetch_comments) === 1 ? 'primary' : 'default'}
                  className="mobile-comment-fetch-action"
                  loading={commentFetchSavingTid === mobileActionThread.tid}
                  onClick={() => {
                    setMobileActionTid('')
                    handleCommentFetch(mobileActionThread.tid, Number(mobileActionThread.fetch_comments) !== 1)
                  }}
                >
                  {Number(mobileActionThread.fetch_comments) === 1 ? '停止抓评' : '抓评'}
                </Button>
              </div>
            </div>
          )}
        </MobileSheet>
    </main>
  )
}
