import { useMemo } from 'react'
import { Button, Dropdown, Space, Tag, Typography } from 'antd'
import { CommentOutlined, EyeOutlined, MessageOutlined, MoreOutlined } from '@ant-design/icons'
import { formatNumber, FEEDBACK_OPTIONS } from '../../shared.jsx'
const { Text } = Typography

export default function useThreadColumns({ showActions, feedbackSavingTid, handleFeedback, isMobile, compactStats, markSeen, openThreadAndMarkSeen, setMobileActionTid }) {
  return useMemo(() => [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      render: (title, record) => (
        <div className="thread-title-cell">
          <div className="thread-title-line">
            <a
              className="thread-title"
              href={record.official_url}
              target="_blank"
              rel="noreferrer"
              title={title}
              onClick={() => markSeen(record.tid)}
            >
              {title}
            </a>
            {Number(record.seen) === 1 && (
              <Tag color="default" className="thread-seen-tag">已看</Tag>
            )}
            {isMobile && showActions && (
              <Button
                type="link"
                size="small"
                className="thread-mobile-action-trigger"
                icon={<MoreOutlined />}
                onClick={() => setMobileActionTid(record.tid)}
                aria-label="帖子操作"
              />
            )}
          </div>
          <div className="thread-row-context">
            <span>{record.forum_name || `fid ${record.fid}`}</span>
            {record.author && <span>{record.author}</span>}
          </div>
          {compactStats && <div className="thread-row-extra-metrics"><span>参与 {formatNumber(record.participant_count)}</span><span>金钱/购买 {formatNumber(record.money)}</span><span>评分 {record.rating || '-'}</span></div>}
          {isMobile && (
            <div className="thread-mobile-stats" aria-label="回复和浏览">
              <span title="回复数">
                <CommentOutlined />
                {formatNumber(record.reply_count)}
              </span>
              <span title="浏览数">
                <EyeOutlined />
                {formatNumber(record.view_count)}
              </span>
            </div>
          )}
        </div>
      ),
    },
    {
      title: '发帖时间',
      dataIndex: 'posted_at',
      key: 'posted_at',
      responsive: ['md'],
      width: 112,
      render: (value) => <Text type="secondary" className="thread-posted-at">{value || '-'}</Text>,
    },
    {
      title: '回复',
      dataIndex: 'reply_count',
      key: 'reply_count',
      className: 'thread-reply-cell',
      responsive: ['md'],
      width: 72,
      align: 'right',
      render: (value) => <Text strong>{formatNumber(value)}</Text>,
    },
    {
      title: '浏览',
      dataIndex: 'view_count',
      key: 'view_count',
      responsive: ['md'],
      width: 72,
      align: 'right',
      render: (value) => formatNumber(value),
    },
    {
      title: '参与',
      dataIndex: 'participant_count',
      key: 'participant_count',
      responsive: ['xl'],
      width: 66,
      align: 'right',
      render: (value) => formatNumber(value),
    },
    {
      title: '金钱/购买',
      dataIndex: 'money',
      key: 'money',
      responsive: ['xl'],
      width: 86,
      align: 'right',
      render: (value) => formatNumber(value),
    },
    {
      title: '评分',
      dataIndex: 'rating',
      key: 'rating',
      responsive: ['xl'],
      width: 62,
      align: 'right',
      render: (value) => value || '-',
    },
    {
      title: '操作',
      dataIndex: 'feedback',
      key: 'actions',
      responsive: ['md'],
      width: compactStats ? 184 : 204,
      render: (value, record) => (
        <Space size={4} wrap className="thread-actions">
          <Button
            size="small"
            type="text"
            icon={<MessageOutlined />}
            onClick={() => openThreadAndMarkSeen(record.tid)}
          >
            评论
          </Button>
          <Button
            size="small"
            type={value === 'dislike' ? 'primary' : 'text'}
            loading={feedbackSavingTid === record.tid && value !== 'dislike'}
            onClick={() => handleFeedback(record.tid, 'dislike', value)}
          >
            不感兴趣
          </Button>
          <Dropdown
            trigger={['click']}
            menu={{
              items: [{
                key: 'like',
                icon: FEEDBACK_OPTIONS.find((option) => option.value === 'like')?.icon,
                label: value === 'like' ? '取消感兴趣' : '感兴趣',
              }],
              onClick: () => handleFeedback(record.tid, 'like', value),
            }}
          >
            <Button size="small" type="text" icon={<MoreOutlined />} aria-label="更多操作" />
          </Dropdown>
        </Space>
      ),
    },
  ].filter((column) => showActions || column.key !== 'actions'), [feedbackSavingTid, handleFeedback, isMobile, compactStats, markSeen, openThreadAndMarkSeen, showActions, setMobileActionTid])

}
