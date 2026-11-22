import { useId, useState } from 'react'
import { Alert, Button, Skeleton } from 'antd'
import { DownOutlined, ReloadOutlined } from '@ant-design/icons'
import InsightThreadLinks from './InsightThreadLinks.jsx'
import useInsights from './useInsights.js'
import { hotPeriodRange } from './filters.js'
import './PeriodInsights.css'

export default function InsightsPreview({ filters, isMobile, active, onOpen, onSeen, seenTids, refreshKey }) {
  const [expanded, setExpanded] = useState(false)
  const bodyId = useId()
  const collapsed = isMobile && !expanded
  const { data, loading, error, refresh } = useInsights(filters, { active, preview: true, refreshKey })
  const range = hotPeriodRange(filters)
  const hasGrowth = Boolean(data?.growth.items.length)
  return <section className={`period-insights insights-preview${collapsed ? ' is-collapsed' : ''}`} aria-label="本期值得看">
    <header className="insights-preview-header">
      <h2>{isMobile ? <button className="insights-preview-toggle" onClick={() => setExpanded(value => !value)} aria-expanded={!collapsed} aria-controls={bodyId}>本期值得看 <DownOutlined rotate={expanded ? 180 : 0} /></button> : '本期值得看'}</h2>
      <p className="insights-preview-scope" hidden={collapsed}>{range.from}—{range.to}<span>当前板块已采集的帖子</span></p>
      <div className="insights-preview-actions">{!collapsed && <Button type="text" icon={<ReloadOutlined />} aria-label="刷新精选" loading={loading} onClick={refresh} />}<Button type="link" onClick={() => onOpen(filters)}>全部分析 →</Button></div>
    </header>
    <div id={bodyId} className="insights-preview-body" hidden={collapsed}>
    {error && <Alert type="warning" showIcon title="精选暂时加载失败" description={error} action={<Button onClick={refresh}>重试</Button>} />}
    {loading && !data && <Skeleton active paragraph={{ rows: 2 }} title={false} />}
    {data && <div className={`insights-preview-grid${hasGrowth ? '' : ' has-quiet-growth'}`} aria-busy={loading}>
      <section className="insights-preview-missed">
        <div className="insights-preview-heading"><h3>漏看精选</h3><Button type="link" onClick={() => onOpen(filters, 'missed')}>更多</Button></div>
        {data.missed.items.length ? <InsightThreadLinks compact items={data.missed.items.slice(0, 1)} {...{ onSeen, seenTids }} /> : <p className="insight-note">本期暂无漏看精选，继续浏览下方帖子。</p>}
      </section>
      <section className={hasGrowth ? 'insights-preview-growth' : 'insights-preview-growth is-empty'}>
        <div className="insights-preview-heading"><h3>热度增长</h3><Button type="link" onClick={() => onOpen(filters, 'growth')}>更多</Button></div>
        {data.growth.items.length ? <InsightThreadLinks compact growth items={data.growth.items.slice(0, 1)} {...{ onSeen, seenTids }} /> : <p className="insight-note">{data.growth.status === 'insufficient' ? '同一帖子采集至少两次后，才能比较增长。' : '本期暂未观测到正增长。'}</p>}
      </section>
    </div>}
    </div>
  </section>
}
