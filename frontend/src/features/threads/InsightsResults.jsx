import { useEffect, useState } from 'react'
import { Alert, Button, Empty, Pagination, Skeleton } from 'antd'
import { requestJson } from '../../api/client.js'
import InsightThreadLinks from './InsightThreadLinks.jsx'

export default function InsightsResults({ selection, page, onPage, onBack, onSeen, seenTids }) {
  const [result, setResult] = useState(null)
  const [retry, setRetry] = useState(0)
  const query = new URLSearchParams({
    page, page_size: 20, sort: 'reply_count', order: 'desc', fid: selection.fid,
    posted_date_from: selection.dateFrom, posted_date_to: selection.dateTo,
    q: selection.q, author_id: selection.authorId, hide_seen: selection.hideSeen ? '1' : '0',
  }).toString()
  const key = `${query}:${retry}`
  const current = result?.key === key ? result : null
  useEffect(() => {
    const controller = new AbortController()
    requestJson(`/api/threads?${query}`, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setResult({ key, data })
    }).catch(error => {
      if (!controller.signal.aborted) setResult({ key, error: error.message })
    })
    return () => controller.abort()
  }, [query, key])
  return <section className="period-insights insights-results" aria-label="分析筛选结果" aria-busy={!current}>
    <p className="insight-note">按回复数排序 · 只使用上方分析条件，不改变首页筛选。打开过的帖子本次保留原位。</p>
    {!current && <Skeleton active paragraph={{ rows: 5 }} />}
    {current?.error && <Alert type="error" showIcon title="帖子加载失败" description={current.error} action={<Button onClick={() => setRetry(value => value + 1)}>重试</Button>} />}
    {current?.data && <>
      <p className="insight-result-count">共 {current.data.total.toLocaleString('zh-CN')} 篇</p>
      {current.data.items.length ? <InsightThreadLinks items={current.data.items} {...{ onSeen, seenTids }} /> : <Empty description="没有符合本次分析条件的帖子"><Button onClick={onBack}>返回分析，调整范围</Button></Empty>}
      <Pagination current={page} pageSize={20} total={current.data.total} showSizeChanger={false} hideOnSinglePage onChange={onPage} />
    </>}
  </section>
}
