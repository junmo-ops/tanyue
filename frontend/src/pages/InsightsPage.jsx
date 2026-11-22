import { useEffect, useMemo, useRef } from 'react'
import { Alert, Button, InputNumber, Select, Skeleton } from 'antd'
import { DownOutlined, LeftOutlined, ReloadOutlined, RightOutlined } from '@ant-design/icons'
import { hotPeriodRange, HOT_DAY_VALUES, MAX_HOT_PERIOD } from '../features/threads/filters.js'
import { insightsUrl, insightResultsUrl, parseInsightsState } from '../features/threads/insightState.js'
import useInsights from '../features/threads/useInsights.js'
import PeriodInsights from '../features/threads/PeriodInsights.jsx'
import InsightsResults from '../features/threads/InsightsResults.jsx'
import ReaderHeader from '../ReaderHeader.jsx'

export default function InsightsPage({ location, onBack, onNavigate, onSeen, seenTids, forums }) {
  const { filters, tab, selection, page } = useMemo(() => parseInsightsState(location), [location])
  const { data, loading, error, refresh } = useInsights(filters, { active: !selection })
  const headingRef = useRef(null)
  const restoredRef = useRef(null)
  const range = hotPeriodRange(filters)
  const forumOptions = [{ value: '', label: '全部板块' }, ...forums.map(item => ({ value: item.fid, label: item.forum_name }))]
  const forumName = fid => forumOptions.find(option => option.value === fid)?.label || fid || '全部板块'
  const inResults = Boolean(selection)

  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true })
  }, [inResults])

  useEffect(() => {
    if (restoredRef.current === location || (!selection && loading)) return
    const frame = window.requestAnimationFrame(() => {
      window.scrollTo({ top: window.history.state?.pageScroll || 0, behavior: 'instant' })
      restoredRef.current = location
    })
    return () => window.cancelAnimationFrame(frame)
  }, [location, loading, selection])

  function updateScope(values) {
    onNavigate(insightsUrl({ ...filters, hot_anchor: range.anchor, ...values }, tab), { replace: true, preserveScroll: true })
  }
  function explore(values) {
    const next = { dateFrom: range.from, dateTo: range.to, fid: filters.fid, ...values }
    onNavigate(insightResultsUrl(filters, tab, next), { fromInsights: true })
  }
  function backToAnalysis() {
    if (window.history.state?.fromInsights) window.history.back()
    else onNavigate(insightsUrl(filters, tab), { replace: true, fromInsights: false })
  }

  return <main className="app-shell thread-list-shell insights-page">
    <ReaderHeader title={inResults ? '分析结果' : '数据分析'} headingRef={headingRef}
      onBack={inResults ? backToAnalysis : onBack} backLabel={inResults ? '返回分析' : '返回帖子'}
      actions={!inResults && <Button type="text" icon={<ReloadOutlined />} loading={loading} onClick={refresh}>刷新分析</Button>} />
    <div className="thread-reader-content reader-content-narrow">
    {inResults ? <>
      <section className="insights-result-scope" aria-label="本次结果范围">
        <span>{selection.dateFrom}—{selection.dateTo}</span><span>{forumName(selection.fid)}</span>
        {selection.authorId && <span>作者：{selection.authorName || selection.authorId}</span>}
        {selection.q && <span>关键词：{selection.q}</span>}
        {selection.hideSeen && <span>进入时尚未标记已看</span>}
      </section>
      <InsightsResults {...{ selection, page, onSeen, seenTids }} onBack={backToAnalysis} onPage={next => onNavigate(insightResultsUrl(filters, tab, selection, next), { replace: true, fromInsights: true })} />
    </> : <>
      <section className="insights-scope-controls" aria-label="分析范围">
        <details className="insights-scope-options">
          <summary><span>{filters.hot_days} 天一期 · {forumName(filters.fid)}</span><span className="insights-scope-toggle">调整范围 <DownOutlined /></span></summary>
        <div className="insights-scope-fields">
          <label htmlFor="insights-forum">板块<Select id="insights-forum" value={filters.fid} options={forumOptions} onChange={fid => updateScope({ fid })} /></label>
          <form className="insights-custom-days" onSubmit={event => {
            event.preventDefault()
            const days = Number(new FormData(event.currentTarget).get('days'))
            if (Number.isInteger(days) && days >= 1 && days <= 365) updateScope({ hot_days: days, hot_period: 0 })
          }}>
            <label htmlFor="insights-days">每期天数<InputNumber key={filters.hot_days} id="insights-days" name="days" min={1} max={365} precision={0} defaultValue={filters.hot_days} /></label>
            <Button htmlType="submit">应用</Button>
          </form>
          <div className="insights-day-shortcuts" aria-label="常用周期">{HOT_DAY_VALUES.map(days => <Button key={days} className="mobile-quiet-action" aria-pressed={filters.hot_days === days} type={filters.hot_days === days ? 'primary' : 'default'} onClick={() => updateScope({ hot_days: days, hot_period: 0 })}>{days} 天</Button>)}</div>
        </div>
        </details>
        <div className="insights-period-controls">
          <Button className="mobile-quiet-action" icon={<LeftOutlined />} aria-label="上一周期" disabled={filters.hot_period >= MAX_HOT_PERIOD} onClick={() => updateScope({ hot_period: filters.hot_period + 1 })} />
          <strong aria-live="polite">{range.from}—{range.to}</strong>
          <Button className="mobile-quiet-action" icon={<RightOutlined />} aria-label="下一周期" disabled={!filters.hot_period} onClick={() => updateScope({ hot_period: filters.hot_period - 1 })} />
          {(filters.hot_period > 0 || range.to !== hotPeriodRange({ ...filters, hot_anchor: '', hot_period: 0 }).to) && <Button className="insights-latest-period" type="link" onClick={() => updateScope({ hot_period: 0, hot_anchor: '' })}>回到最近</Button>}
        </div>
      </section>
      {error && <Alert type="error" showIcon title="分析加载失败" description={error} action={<Button onClick={refresh}>重试</Button>} />}
      {loading && !data && <section className="period-insights insights-loading" role="status"><Skeleton active paragraph={{ rows: 5 }} /><span>正在整理本期数据…</span></section>}
      {data && <>
        {loading && <p className="insight-note" role="status">正在刷新分析，暂时保留上次结果…</p>}
        {error && <p className="insight-note">以下保留上次成功获取的结果，可能不是最新数据。</p>}
        <PeriodInsights {...{ data, tab, onSeen, seenTids }} onExplore={explore} onTab={next => onNavigate(insightsUrl(filters, next), { replace: true, preserveScroll: true })} />
      </>}
    </>}
    </div>
  </main>
}
