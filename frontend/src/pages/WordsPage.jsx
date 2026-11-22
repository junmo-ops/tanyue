import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Empty, Skeleton, Spin } from 'antd'
import { SyncOutlined, TagsOutlined } from '@ant-design/icons'
import { requestJson } from '../api/client.js'
import ReaderHeader from '../ReaderHeader.jsx'

// Retain the batch across route changes, but start fresh on a browser reload.
let savedBatch = null
let pendingBatch = null
function fetchBatch() {
  if (!pendingBatch) {
    pendingBatch = requestJson('/api/title-words?mode=random').then(payload => {
      if (payload.mode !== 'random') throw new Error('请重启主机上的 forum_api.py，以启用随机发现。')
      savedBatch = payload.items
      return savedBatch
    }).finally(() => { pendingBatch = null })
  }
  return pendingBatch
}

export default function WordsPage({ onBackToThreads }) {
  const [items, setItems] = useState(savedBatch || [])
  const [loading, setLoading] = useState(savedBatch === null)
  const [error, setError] = useState('')
  const mounted = useRef(false)

  useEffect(() => {
    mounted.current = true
    if (savedBatch === null || pendingBatch) {
      fetchBatch().then(batch => { if (mounted.current) setItems(batch) })
        .catch(err => { if (mounted.current) setError(err.message) })
        .finally(() => { if (mounted.current) setLoading(false) })
    }
    return () => { mounted.current = false }
  }, [])

  async function shuffle() {
    setLoading(true)
    setError('')
    try {
      const batch = await fetchBatch()
      if (mounted.current) setItems(batch)
    } catch (err) {
      if (mounted.current) setError(err.message)
    } finally {
      if (mounted.current) setLoading(false)
    }
  }

  return <main className="app-shell thread-list-shell discovery-shell">
    <ReaderHeader title="随机发现" icon={<TagsOutlined className="header-icon" />} onBack={() => onBackToThreads()}
      actions={<Button type="text" icon={<SyncOutlined />} loading={loading} onClick={shuffle}>换一批</Button>} />
    <div className="thread-reader-content reader-content-narrow">
    <p className="reader-context-note">点一个感兴趣的词，发现相关帖子</p>
    <section className="discovery-panel" aria-label="随机词语">
      {error && <Alert type="error" showIcon title={error} />}
      {loading && !items.length ? <div className="discovery-loading" role="status"><Skeleton active title={false} paragraph={{ rows: 4 }} /><p>正在整理可发现的词语…</p></div> : <Spin spinning={loading}>
        <div className="discovery-tags" aria-busy={loading}>
          {items.map(({ word }) => <button key={word} className="discovery-tag" onClick={() => onBackToThreads(word)}>{word}</button>)}
          {!loading && !error && !items.length && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无可推荐的词语，采集更多帖子后再来看看" />}
        </div>
      </Spin>}
    </section>
    </div>
  </main>
}
