import { MoreOutlined, RightOutlined } from '@ant-design/icons'
import { useControls } from '../../useControls.js'
import { formatNumber } from '../../shared.jsx'

const jobDate = new Intl.DateTimeFormat('sv-SE', {
  dateStyle: 'short', timeStyle: 'short',
})

const units = { sync: '页', details: '帖', comments: '页', rankings: '份' }

function progressText(job) {
  const { completed, total, total_known: totalKnown } = job.progress
  return '完成 ' + formatNumber(completed) + (totalKnown ? ' / '+formatNumber(total) : '') + ' ' + (units[job.kind] ?? '项')
}

function submittedTime(value) {
  if (!value) return '—'
  const date = new Date(value.replace(' ', 'T')+'Z')
  return Number.isNaN(date.getTime()) ? '—' : jobDate.format(date)
}

function resultText(job) {
  if (job.status === 'queued') return '等待前序任务完成'
  const progress = job.progress
  if (!progress) return '—'
  const parts = []
  if (job.status === 'running' || job.status === 'stopping' || job.kind === 'details') {
    parts.push(progressText(job))
  }
  if (job.kind === 'sync') parts.push('新增 '+formatNumber(progress.new)+' · 更新 '+formatNumber(progress.updated))
  if (job.kind === 'comments') parts.push('保存 '+formatNumber(progress.saved_comments)+' 条评论')
  if (job.kind === 'rankings') parts.push('保存 '+formatNumber(progress.completed)+' 份榜单')
  if (progress.failed) parts.push('失败 '+formatNumber(progress.failed)+' '+(units[job.kind] ?? '项'))
  return parts.join(' · ') || '—'
}

function taskMetrics({ kind, progress }) {
  const failures = ['失败'+({ sync: '页数', details: '帖子', comments: '页数', rankings: '榜单' }[kind] ?? '数'), progress.failed]
  if (kind === 'sync') return [['新增帖子', progress.new], ['更新帖子', progress.updated], failures]
  if (kind === 'comments') return [['保存评论', progress.saved_comments], ['已完成帖子', progress.threads_completed], failures]
  return [[kind === 'rankings' ? '保存榜单' : '已完成帖子', progress.completed], failures]
}

function JobStatus({ job, labels }) {
  return <span className="crawl-console-tag" data-status={job.status}>{labels[job.status] ?? job.status}</span>
}

export function CrawlCurrentTask({ job, title, labels, onQueue, onDetails, action }) {
  const { Button } = useControls()
  const summary = job.progress
  const percent = summary?.total_known && summary.total > 0
    ? Math.min(100, Math.max(0, Math.round(100 * (summary.completed ?? 0) / summary.total)))
    : null
  return <section className="crawl-console-panel crawl-console-task" aria-labelledby="crawl-current-title">
    <div className="crawl-console-panel-head">
      <h2 id="crawl-current-title">当前任务</h2>
      <Button type="link" onClick={onQueue}>查看队列 <RightOutlined /></Button>
    </div>
    <div className="crawl-console-task-title"><h3>{title}</h3><JobStatus job={job} labels={labels} /></div>
    {summary && job.status !== 'queued' ? <>
      <div className="crawl-console-progress-summary">
        <span>{progressText(job)}{percent === null && ' · 总量待定'}</span>
        {percent !== null && <strong>{percent}%</strong>}
      </div>
      {percent !== null && <progress className="crawl-console-progress" max={100} value={percent} aria-label="采集进度" />}
      <div className="crawl-console-job-metrics">
        {taskMetrics(job).map(([label, value]) => <div key={label}><span>{label}</span><strong>{formatNumber(value)}</strong></div>)}
      </div>
    </> : <p className="crawl-console-muted">{job.status === 'queued' ? '已加入队列，等待执行。' : '正在读取任务进度…'}</p>}
    <div className="crawl-console-task-actions"><Button type="link" onClick={onDetails}>任务详情</Button>{action}</div>
  </section>
}

export function CrawlRecords({ overview, records, filterOptions, filter, onFilter, count, page,
  onPage, onAll, onDetails, onStop, onResume, busy, stopping, offline, kinds, labels }) {
  const { Button, Dropdown, Empty, Pagination, Segmented } = useControls()
  const title = overview ? '最近采集结果' : '任务记录'

  return <section className="crawl-console-records" aria-labelledby="crawl-records-title">
    {!overview && <div className="crawl-console-records-title">
      <h2 id="crawl-records-title">{title}</h2><span>保留最近 30 次历史</span>
    </div>}
    <div className="crawl-console-panel">
      {overview ? <div className="crawl-console-panel-head crawl-console-table-head">
        <h2 id="crawl-records-title">{title}</h2>
        <Button type="link" onClick={onAll}>全部记录 <RightOutlined /></Button>
      </div> : <div className="crawl-console-filterbar">
        <Segmented aria-label="任务记录筛选" options={filterOptions} value={filter} onChange={onFilter} />
        <span>显示 {records.length} 条</span>
      </div>}
      {records.length ? <div className="crawl-console-table-scroll">
        <table className="crawl-console-table" aria-labelledby="crawl-records-title">
          <colgroup><col className="crawl-column-task" /><col className="crawl-column-state" /><col className="crawl-column-time" /><col className="crawl-column-result" /><col className="crawl-column-action" /></colgroup>
          <thead><tr>{['任务', '状态', '提交时间', '结果', '操作'].map(label => <th key={label} scope="col">{label}</th>)}</tr></thead>
          <tbody>{records.map(job => {
            const canResume = ['failed', 'partial', 'interrupted', 'cancelled'].includes(job.status)
            const canStop = ['running', 'queued'].includes(job.status)
            const taskName = kinds[job.kind] ?? job.kind
            return <tr key={job.id}>
              <td><strong>{taskName}</strong></td>
              <td><JobStatus job={job} labels={labels} /></td>
              <td>{submittedTime(job.created_at)}</td>
              <td>{resultText(job)}</td>
              <td><div className="crawl-console-row-actions">
                <Button type="link" onClick={() => onDetails(job.id)} aria-label={'详情：'+taskName}>详情</Button>
                {canResume && <Button className="crawl-console-resume" type="text" disabled={offline}
                  loading={busy} onClick={() => onResume(job.id)}>继续未完成</Button>}
                {canStop && <Dropdown trigger={['click']} menu={{
                  items: [{ key: 'stop', danger: true, label: job.status === 'queued' ? '取消排队' : '停止任务' }],
                  onClick: () => onStop(job.id),
                }}>
                  <Button type="text" className="crawl-console-more" icon={<MoreOutlined />} disabled={offline || stopping === job.id}
                    aria-label={taskName+'的更多操作'} aria-haspopup="menu" />
                </Dropdown>}
              </div></td>
            </tr>
          })}</tbody>
        </table>
      </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={overview ? '还没有采集结果，从常用方案开始吧' : '没有符合条件的任务'} />}
      {!overview && count > 8 && <Pagination className="crawl-record-pagination" simple
        current={page} pageSize={8} total={count} onChange={onPage} showSizeChanger={false} />}
    </div>
  </section>
}
