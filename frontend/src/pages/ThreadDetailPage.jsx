import { siteFetch } from '../api/site.js'
import { useEffect, useMemo, useState } from 'react'
import { useControls } from '../useControls.js'
import { ExportOutlined, MessageOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import { COMMENT_PAGE_SIZE_OPTIONS, formatNumber, splitKeywords } from '../shared.jsx'

import useCommentTask from '../features/threads/useCommentTask.js'
import ReaderHeader from '../ReaderHeader.jsx'


function highlightCommentText(value, keywords) {
  const text = String(value || '-')
  if (!keywords.length) return text
  const escaped = keywords.map((keyword) => keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const pattern = new RegExp(`(${escaped.join('|')})`, 'gi')
  return text.split(pattern).map((part, index) => (
    keywords.some((keyword) => keyword === part.toLowerCase())
      ? <mark className="comment-keyword-mark" key={`${part}-${index}`}>{part}</mark>
      : part
  ))
}

export default function ThreadDetailPage({ tid, onBack }) {
  const { Alert, Button, Empty, Form, Input, List, Pagination, Progress, Select, Space, message, Typography } = useControls()
  const { Text, Title } = Typography
  const [detail, setDetail] = useState({ thread: null, comments: [] })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const { run: fetchComments, running: fetchingComments, progress: commentProgress } = useCommentTask(tid)
  const [filters, setFilters] = useState({ q: '', exclude_q: '', page_size: 50 })
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [form] = Form.useForm()

  useEffect(() => {
    let ignore = false
    const controller = new AbortController()

    async function loadDetail() {
      setLoading(true)
      setError('')
      try {
        const query = new URLSearchParams({ tid, page, ...filters })
        const response = await siteFetch(`/api/thread?${query}`, { signal: controller.signal })
        const payload = await response.json()
        if (ignore) {
          return
        }
        if (!response.ok) {
          throw new Error(payload.error || '评论加载失败')
        }
        setDetail(payload)
      } catch (error) {
        if (!ignore) {
          setError(error.message)
          setDetail({ thread: null, comments: [] })
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    loadDetail()
    return () => {
      ignore = true
      controller.abort()
    }
  }, [tid, filters, page, revision])

  const comments = useMemo(() => detail.comments || [], [detail.comments])
  const highlightKeywords = useMemo(() => splitKeywords(filters.q), [filters.q])
  const handleCommentSearch = (values) => {
    setFilters({
      q: values.q || '',
      exclude_q: values.exclude_q || '',
      page_size: values.page_size || 50,
    })
    setPage(1)
  }
  const handleCommentReset = () => {
    form.resetFields()
    setFilters({ q: '', exclude_q: '', page_size: 50 })
    setPage(1)
  }

  const handleFetchComments = async () => {
    try {
      const payload = await fetchComments()
      if (!payload) return
      setPage(1)
      setRevision(value => value + 1)
      message.success(`已抓取 ${formatNumber(payload.total_comments || 0)} 条评论`)
    } catch (error) {
      if (error.name !== 'AbortError') message.error(error.message)
    }
  }

  return (
    <main className="app-shell thread-list-shell detail-shell detail-reading-shell">
      <ReaderHeader title="帖子详情" onBack={onBack} />
      <div className="thread-reader-content reader-content-narrow">
      {error && <Alert className="reader-load-error" type="error" showIcon title="评论加载失败" description={error} action={<Button onClick={() => setRevision(value => value + 1)}>重试</Button>} />}
      <section className="detail-hero">
        <div className="detail-heading">
          <Title level={1}>{detail.thread?.title || '帖子详情'}</Title>
          {detail.thread && (
            <div className="detail-thread-meta">
              <span>{detail.thread.forum_name || `fid ${detail.thread.fid}`}</span>
              <span>{detail.thread.author || '匿名'}</span>
              <span>{detail.thread.posted_at || '-'}</span>
              <span>{formatNumber(detail.thread.reply_count)} 回复</span>
              <span>{formatNumber(detail.thread.view_count)} 浏览</span>
              {detail.thread.reward_money != null && <span>{formatNumber(detail.thread.reward_money)} 金钱</span>}
              {detail.thread.purchase_count != null && <span>{formatNumber(detail.thread.purchase_count)} 人购买</span>}
              <a href={detail.thread.official_url} target="_blank" rel="noreferrer">
                打开原帖 <ExportOutlined />
              </a>
            </div>
          )}
        </div>
        <div className="detail-comment-count">
          <strong>{formatNumber(detail.total || 0)}</strong>
          <span>条评论</span>

        </div>
      </section>

      <section className="detail-panel reading-panel">
        <Form
          form={form}
          layout="inline"
          initialValues={filters}
          onFinish={handleCommentSearch}
          className="comment-filter-form reading-filter-form"
        >
          <Form.Item name="q">
            <Input
              allowClear
              aria-label="评论关键词"
              prefix={<SearchOutlined />}
              placeholder="评论关键词"
              className="comment-filter-input"
            />
          </Form.Item>
          <Form.Item name="exclude_q">
              <Input
                allowClear
                aria-label="排除评论关键词"
                placeholder="排除关键词"
                className="comment-filter-input"
              />
            </Form.Item>
          <Form.Item name="page_size">
            <Select
              aria-label="每页评论数量"
              options={COMMENT_PAGE_SIZE_OPTIONS}
              className="comment-page-size-select"
            />
          </Form.Item>
          <Form.Item className="comment-filter-actions">
            <Space size={8}>
              <Button type="primary" htmlType="submit" icon={<SearchOutlined />}>
                筛选评论
              </Button>
              <Button className="mobile-quiet-action" icon={<ReloadOutlined />} onClick={handleCommentReset}>
                重置
              </Button>
            </Space>
          </Form.Item>
        </Form>
        <div className="comment-section-title reading-section-title">
          <div>
            <MessageOutlined />
            <Title level={4}>评论内容</Title>
          </div>
          <Text type="secondary">
            {formatNumber(detail.total || 0)} / {formatNumber(detail.total_comments || 0)} 条
          </Text>
          {!!detail.total_comments && (
            <Button className="mobile-quiet-action" size="small" loading={fetchingComments} onClick={handleFetchComments}>更新评论</Button>
          )}
        </div>
        {fetchingComments && (
          <div className="comment-fetch-status">
            <Progress
              percent={commentProgress.percent || 0}
              size="small"
              status={commentProgress.status === 'failed' ? 'exception' : 'active'}
            />
            <Text type="secondary">
              {commentProgress.total_pages
                ? `正在抓取评论 ${commentProgress.completed_pages}/${commentProgress.total_pages} 页，已入库 ${formatNumber(commentProgress.saved_comments)} 条`
                : '正在读取评论分页信息...'}
            </Text>
          </div>
        )}
        <List
          loading={loading}
          dataSource={comments}
          locale={{
            emptyText: (
              <Empty description={error ? '请重试加载评论' : detail.total_comments ? '没有符合条件的评论' : '本地还没有评论'}>
                {!error && !detail.total_comments && <Button type="primary" icon={<MessageOutlined />} loading={fetchingComments} onClick={handleFetchComments}>
                  抓取评论
                </Button>}
              </Empty>
            ),
          }}
          className="reading-comment-list"
          renderItem={(comment, index) => (
            <List.Item className="comment-item">
              <div className="comment-author-mark" aria-hidden="true">
                {(comment.author || '匿').slice(0, 1)}
              </div>
              <div className="comment-reading-body">
                <div className="comment-reading-meta">
                  <Text strong>{comment.author || '匿名'}</Text>
                  <span>#{((detail.page || page) - 1) * (filters.page_size || 50) + index + 1}</span>
                  {comment.posted_at && <span>{comment.posted_at}</span>}
                </div>
                <div className="comment-content">{highlightCommentText(comment.content_text, highlightKeywords)}</div>
              </div>
            </List.Item>
          )}
        />
        <Pagination
          current={detail.page || page}
          pageSize={detail.page_size || filters.page_size || 50}
          total={detail.total || 0}
          showSizeChanger={false}
          disabled={loading}
          showTotal={(total, range) => `${range[0]}-${range[1]} / ${total} 条`}
          onChange={setPage}
        />
      </section>
      </div>
    </main>
  )
}
