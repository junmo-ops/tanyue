import { useEffect, useRef, useState } from 'react'
import { useControls } from '../../useControls.js'

const kinds = { sync: '同步帖子列表', details: '补全帖子详情', comments: '抓取已开启的评论', rankings: '采集排行榜' }
const states = { queued: '排队中', running: '运行中', stopping: '正在停止', cancelled: '已停止', succeeded: '已完成', partial: '部分失败', failed: '失败', interrupted: '服务中断' }
const time = value => value ? new Date(`${value.replace(' ', 'T')}Z`).toLocaleString('zh-CN', { hour12: false }) : '—'

export function JobResult({ job, observedAt }) {
  const { Progress, Typography } = useControls()
  const summary = job.progress
  const elapsed = job.started_at ? Math.max(0, Math.floor(((job.finished_at ? new Date(`${job.finished_at.replace(' ', 'T')}Z`).getTime() : observedAt) - new Date(`${job.started_at.replace(' ', 'T')}Z`).getTime()) / 1000)) : 0
  if (!summary || job.status === 'queued') return <Typography.Paragraph type="secondary">已加入队列，前面的任务结束后自动执行。</Typography.Paragraph>
  return <>
    {job.kind !== 'rankings' && <div className="crawl-result-metrics">
      <div><span>新增帖子</span><strong>{summary.new}</strong></div>
      <div><span>更新帖子</span><strong>{summary.updated}</strong></div>
      <div><span>保存评论</span><strong>{summary.saved_comments}</strong></div>
    </div>}
    <Typography.Paragraph type="secondary">完成 {summary.completed}{summary.total_known ? ` / ${summary.total}` : ''} {({ details: '帖', rankings: '份榜单' })[job.kind] || '页'} · 失败 {summary.failed} · 耗时 {elapsed < 60 ? `${elapsed} 秒` : `${Math.floor(elapsed / 60)} 分 ${elapsed % 60} 秒`}</Typography.Paragraph>
    {summary.total_known && summary.total > 0 ? <Progress percent={Math.round(100 * summary.completed / summary.total)} status={['failed', 'partial'].includes(job.status) ? 'exception' : job.status === 'running' ? 'active' : 'normal'} /> : job.status === 'running' && <Typography.Paragraph type="secondary">{job.kind === 'sync' ? '正在增量同步，总页数随采集进度确定。' : job.kind === 'rankings' ? '正在连接论坛。' : '正在读取评论页数。'}</Typography.Paragraph>}
    {job.kind === 'comments' && <Typography.Paragraph type="secondary">已完成帖子 {summary.threads_completed} / {summary.threads_total}</Typography.Paragraph>}
  </>
}

export default function JobDetail({ job, observedAt, actions, onBack }) {
  const { Alert, Button, Collapse, Descriptions, Space, Switch, Tag, Typography, message } = useControls()
  const [follow, setFollow] = useState(true)
  const [expanded, setExpanded] = useState([])
  const logRef = useRef(null)
  useEffect(() => {
    if (follow && logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [job.log, follow, expanded])
  async function copyLog() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
      await navigator.clipboard.writeText(job.log || '')
      message.success('日志已复制')
    } catch { message.info('当前浏览器不支持直接复制，请在日志中长按或选中文字复制。') }
  }
  return <div className="crawl-job-detail">
    <div className="crawl-task-heading"><Typography.Title level={4} style={{ margin: 0 }}>{kinds[job.kind]}</Typography.Title><Tag>{states[job.status] || job.status}</Tag></div>
    <JobResult job={job} observedAt={observedAt} />
    <Space wrap className="crawl-job-actions"><Button className="mobile-quiet-action" onClick={onBack}>查看帖子列表</Button>{actions}</Space>
    {job.progress?.errors?.length > 0 && <Alert type="warning" showIcon title={`${job.progress.failed} 个采集单元失败，继续任务会跳过成功部分`} description={job.progress.errors.slice(0, 5).map((e) => `${e.target}${e.page ? ` 第 ${e.page} 页` : ''}：${e.error}`).join('；')} />}
    {job.status === 'interrupted' && <Alert type="warning" showIcon title="服务中断，已采集数据保留，可继续未完成部分。" />}
    <Descriptions column={1} size="small" items={[
      {key:'created',label:'提交时间',children:time(job.created_at)},
      {key:'finished',label:'结束时间',children:time(job.finished_at)},
      {key:'params',label:'采集范围',children:Object.entries(job.params || {}).map(([key, value]) => `${({fid:'板块',pages:'每板块页数',start_page:'起始页',limit:'帖子上限',tids:'帖子 ID'})[key] || key}：${value}`).join('；') || '使用提交时的默认配置'},
    ]} />
    <Collapse activeKey={expanded} onChange={setExpanded} items={[{key:'log',label:'原始运行日志',children:<>
      <div className="crawl-log-tools"><Space><Switch size="small" checked={follow} onChange={setFollow} aria-label="跟随最新日志" /><span>跟随最新</span></Space><Button className="mobile-quiet-action" size="small" onClick={copyLog}>复制日志</Button></div>
      <pre ref={logRef} className="crawl-log" aria-label="采集任务日志" tabIndex={0}>{job.log || '暂无日志'}</pre>
    </>}]} />
  </div>
}
