const number = value => Number(value || 0).toLocaleString('zh-CN')
const timeLabel = value => new Date(value).toLocaleString('zh-CN', { hour12: false })

export default function InsightThreadLinks({ items = [], onSeen, seenTids = {}, growth = false, compact = false }) {
  return <ul className={`insight-thread-list${compact ? ' is-compact' : ''}`}>
    {items.map(item => <li key={item.tid}>
      <a className="insight-thread-title" href={item.official_url} target="_blank" rel="noopener noreferrer" onClick={() => onSeen(item.tid)}>
        {item.title}<span className="sr-only">（在新标签页打开原帖）</span>
      </a>
      <div className="insight-thread-meta">
        <span>{item.forum_name || '未分类'}</span>
        {!compact && <span>{item.posted_at?.slice(0, 10) || '日期未知'}</span>}
        <span>{number(item.reply_count)} 回复</span>
        <span className={item.seen || seenTids[item.tid] ? 'insight-seen' : ''}>{item.seen || seenTids[item.tid] ? '已打开' : '未打开'}</span>
        {item.feedback === 'like' && <span>感兴趣</span>}
      </div>
      {growth ? <div className="insight-growth-detail">
        <strong>回复 +{number(item.reply_growth)}</strong><span>浏览 +{number(item.view_growth)}</span>
        {!compact && <small>{timeLabel(item.from)} → {timeLabel(item.to)}</small>}
      </div> : !compact && item.reason ? <p className="insight-reason">{item.reason}</p> : null}
    </li>)}
  </ul>
}
