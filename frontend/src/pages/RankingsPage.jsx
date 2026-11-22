import { siteUrl } from '../api/site.js'
import { useEffect, useRef, useState } from 'react'
import { Grid, Table } from 'antd'
import { useControls } from '../useControls.js'
import { ArrowLeftOutlined, TrophyOutlined } from '@ant-design/icons'
import { requestJson } from '../api/client.js'
import ThemeToggle from '../ThemeToggle.jsx'
import './RankingsPage.css'
import RankingDatePicker from './RankingDatePicker.jsx'

const metrics = [
  { value: 'replies', label: '回复', title: '', unit: '回复数' },
  { value: 'views', label: '查看', title: '', unit: '查看数' },
  { value: 'sharetimes', label: '分享', title: '', unit: '分享数' },
  { value: 'favtimes', label: '收藏', title: '', unit: '收藏数' },
  { value: 'heats', label: '热度', title: '', unit: '热度' },
]
const periods = [
  { value: 'today', label: '今日', title: '' },
  { value: 'thisweek', label: '本周', title: '' },
  { value: 'thismonth', label: '本月', title: '' },
  { value: 'all', label: '全部', title: '' },
]
const activeStatuses = ['queued', 'running', 'stopping']
const timeFormat = new Intl.DateTimeFormat('zh-CN', {
  dateStyle: 'medium', timeStyle: 'medium', hour12: false, timeZone: 'Asia/Shanghai',
})
const countFormat = new Intl.NumberFormat('zh-CN')
const formatTime = timestamp => timeFormat.format(new Date(timestamp))
const rankClass = rank => rank <= 3 ? 'rankings-position is-leading' : 'rankings-position'

function RankedThread({ entry, mobile = false }) {
  return <>
    <a className={mobile ? 'mobile-thread-title' : 'thread-title rankings-title'} href={entry.url} target="_blank" rel="noreferrer">{entry.title}</a>
    {(entry.forum || entry.author_and_date) && (
      <div className={mobile ? 'mobile-thread-meta' : 'rankings-meta'}>
        {entry.forum && <span>{entry.forum}</span>}
        {entry.author_and_date && <span>{entry.author_and_date}</span>}
      </div>
    )}
  </>
}

export default function RankingsPage({ location, onBack, onNavigate }) {
  const { Alert, Button, Segmented, Skeleton } = useControls()
  const isMobile = !Grid.useBreakpoint().md
  const params = new URLSearchParams(location.split('?')[1])
  const metric = metrics.find(item => item.value === params.get('metric')) || metrics[0]
  const period = periods.find(item => item.value === params.get('period')) || periods[0]
  const snapshot = params.get('snapshot') || ''
  const query = new URLSearchParams({ metric: metric.value, period: period.value, ...(snapshot && { snapshot }) }).toString()
  const [response, setResponse] = useState(null)
  const [failure, setFailure] = useState(null)
  const [revision, setRevision] = useState(0)
  const heading = useRef(null)
  const data = response?.query === query ? response.data : null
  const error = failure?.query === query ? failure.message : ''
  const job = data?.job
  const active = activeStatuses.includes(job?.status)

  useEffect(() => {
    heading.current?.focus({ preventScroll: true })
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    let timer
    async function load() {
      try {
        const result = await requestJson(`/api/rankings?${query}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setResponse({ query, data: result })
        setFailure(null)
        if (activeStatuses.includes(result.job?.status)) timer = setTimeout(load, 2000)
      } catch (cause) {
        if (!controller.signal.aborted) setFailure({ query, message: cause.message })
      }
    }
    load()
    return () => {
      controller.abort()
      clearTimeout(timer)
    }
  }, [query, revision])

  function select(nextMetric, nextPeriod, nextSnapshot = '') {
    const next = new URLSearchParams({ metric: nextMetric, period: nextPeriod })
    if (nextSnapshot) next.set('snapshot', nextSnapshot)
    onNavigate(next.toString())
  }

  const columns = [
    { title: '名次', dataIndex: 'rank', width: 72, align: 'center', render: rank => <span className={rankClass(rank)}>{rank}</span> },
    { title: '帖子', key: 'thread', render: (_, entry) => <RankedThread entry={entry} /> },
    { title: metric.unit, dataIndex: 'value', width: 112, align: 'right', render: value => <span className="rankings-value">{countFormat.format(value)}</span> },
  ]

  return (
    <main className="app-shell thread-list-shell rankings-page">
      <header className="thread-hero">
        <div className="thread-hero-copy">
          <div className="thread-hero-title">
            <TrophyOutlined className="header-icon" aria-hidden="true" />
            <h1 className="ant-typography" ref={heading} tabIndex={-1}>论坛排行榜</h1>
            <ThemeToggle />
          </div>
        </div>
        <div className="thread-hero-actions">
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回帖子</Button>
        </div>
      </header>

      <div className="thread-reader-content">
        <section className="thread-query-panel" aria-label="榜单筛选">
          <div className="browse-mode-row">
            <div className="browse-mode-control">
              <Segmented aria-label="排行指标" options={metrics} value={metric.value} onChange={next => select(next, period.value)} />
            </div>
          </div>
          <div className="rankings-controls">
            <Segmented aria-label="榜单周期" options={periods} value={period.value} onChange={next => select(metric.value, next)} />
            <RankingDatePicker snapshots={data?.snapshots || []} snapshot={snapshot} isMobile={isMobile}
              onChange={next => select(metric.value, period.value, next)} />
          </div>
        </section>

        <section className="rankings-results" aria-label="榜单结果">
          {data && <div className="rankings-caption">
            <span>{data.snapshot ? `采集于 ${formatTime(data.snapshot.captured_at)}（北京时间）` : '榜单数据来自论坛'}</span>
            <Button className="mobile-quiet-action" type="text" href={data.source_url} target="_blank" rel="noreferrer">查看原榜</Button>
          </div>}

          <div aria-live="polite">
            {active && <p className="rankings-progress">{job.status === 'queued' ? '等待采集' : `已采集 ${job.completed} / ${job.total} 份榜单${job.failed ? ` · 失败 ${job.failed} 份` : ''}`}</p>}
          </div>
          {error && <Alert className="rankings-alert" type="error" showIcon title="榜单读取失败" description={error} action={<Button size="small" onClick={() => {
            setFailure(null)
            if (snapshot && !data) select(metric.value, period.value)
            setRevision(current => current + 1)
          }}>{snapshot && !data ? '查看最新' : '重试'}</Button>} />}
          {job?.error && <Alert className="rankings-alert" type="error" showIcon title="采集未能完成" description={job.error} />}
          {['cancelled', 'interrupted'].includes(job?.status) && <Alert className="rankings-alert" type="warning" showIcon
            title={job.status === 'cancelled' ? '上次采集已停止' : '上次采集已中断'}
            description="已保存的快照可以继续查看，采集管理中可继续未完成的任务。"
          />}
          {!active && job?.failed > 0 && <Alert className="rankings-alert" type="warning" showIcon
            title={`最近一次采集失败 ${job.failed} / ${job.total} 份`}
            description={job.scope_error ? `当前榜单 · ${job.scope_error}${data.snapshot && !snapshot ? '。下方显示上次成功采集的快照。' : ''}` : undefined}
          />}

          {!data && !error && <div className="rankings-empty" role="status" aria-label="正在读取榜单"><Skeleton active paragraph={{ rows: 4 }} /></div>}
          {data?.entries.length > 0 && (isMobile ? (
            <div className="mobile-thread-panel">
              <div className="mobile-thread-list">
                {data.entries.map(entry => (
                  <article className="mobile-thread-item" key={entry.tid}>
                    <div className="mobile-thread-main"><RankedThread entry={entry} mobile /></div>
                    <div className="mobile-thread-metrics">
                      <span className={rankClass(entry.rank)}>第 {entry.rank} 名</span>
                      <span>{countFormat.format(entry.value)} {metric.label}</span>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : (
            <div className="table-panel thread-table-panel">
              <Table rowKey="tid" columns={columns} dataSource={data.entries} size="middle" pagination={false} />
            </div>
          ))}
          {data && !data.entries.length && <div className="rankings-empty">
            <strong>{data.snapshot ? '原站这份榜单没有帖子' : active ? '正在等待这份榜单' : '暂无榜单快照'}</strong>
            {!data.snapshot && !active && <p>可前往<a href={siteUrl('/admin')}>采集管理</a>获取榜单。</p>}
          </div>}
        </section>
      </div>
    </main>
  )
}
