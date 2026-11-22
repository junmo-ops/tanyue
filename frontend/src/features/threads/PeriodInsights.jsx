import { useId } from 'react'
import { useControls } from '../../useControls.js'
import ThreadLinks from './InsightThreadLinks.jsx'
import { INSIGHT_TABS as TABS } from './insightState.js'
import './PeriodInsights.css'

const number = value => Number(value || 0).toLocaleString('zh-CN')
const percent = value => `${Number(value || 0).toFixed(1)}%`
function timeLabel(value) {
  if (!value) return '尚无记录'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString('zh-CN', { hour12: false })
}


function Overview({ data, onExplore, onTab }) {
  const { Empty } = useControls()
  const { overview, period } = data
  const dailyMax = Math.max(1, ...overview.daily.map(item => item.count))
  const forumMax = Math.max(1, ...overview.forums.map(item => item.count))
  return <>
    <div className="insight-metrics">
      <button className="insight-metric" onClick={() => onExplore({})}><span>本期收录新帖</span><strong>{number(overview.total)}</strong><small>按发帖日期统计</small></button>
      <button className="insight-metric" onClick={() => onExplore({ hideSeen: true })}><span>尚未标记已看</span><strong>{number(overview.unseen)}</strong><small>点击查看本期帖子</small></button>
      <div className="insight-metric"><span>标记感兴趣</span><strong>{number(overview.liked)}</strong><small>当前已有兴趣标记</small></div>
    </div>
    <div className="insight-quick-links">
      <button onClick={() => onTab('missed')}>看看本期漏看精选 <span>→</span></button>
      <button onClick={() => onTab('topics')}>发现本期话题变化 <span>→</span></button>
    </div>
    <p className="insight-note">上一周期（{period.previous_from}—{period.previous_to}）收录 {number(overview.previous_total)} 篇。两期采集范围可能不同，数量不代表全站涨跌。</p>
    {!overview.total ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本期暂无已采集帖子，可切换周期或板块" /> : <div className="insight-charts">
      <section>
        <h3>每天收录的帖子</h3>
        <p className="insight-note">按发帖日期分布，点击查看当天帖子</p>
        <div className="insight-daily-chart" aria-label="每日帖子数量，可横向滚动">
          {overview.daily.map(item => <button className="insight-day" key={item.date} aria-label={`${item.date}：${number(item.count)} 篇，查看帖子`} onClick={() => onExplore({ dateFrom: item.date, dateTo: item.date })}>
            <span className="insight-day-count">{number(item.count)}</span>
            <span className="insight-day-track"><span style={{ height: `${Math.max(item.count ? 3 : 0, item.count / dailyMax * 100)}%` }} /></span>
            <span className="insight-day-label">{item.date.slice(5)}</span>
          </button>)}
        </div>
      </section>
      <section>
        <h3>板块分布</h3>
        <p className="insight-note">点击板块查看本期帖子</p>
        <div className="insight-forum-chart">{overview.forums.map(item => <button key={item.fid} onClick={() => onExplore({ fid: item.fid })}>
          <span>{item.forum_name || '未分类'}</span><strong>{number(item.count)} 篇</strong>
          <span className="insight-forum-track"><span style={{ width: `${item.count / forumMax * 100}%` }} /></span>
        </button>)}</div>
      </section>
    </div>}
  </>
}

function Missed({ data, onExplore, onSeen, seenTids }) {
  const { Empty } = useControls()
  return <>
    <div className="insight-section-intro"><p>精选 {number(data.total)} 篇 · 展示前 {number(data.items.length)} 篇</p><button onClick={() => onExplore({ hideSeen: true })}>查看全部未看</button></div>
    <details className="insight-explanation"><summary>筛选说明 · 已打开的帖子刷新后移除</summary><p>从同板块、同发帖日的帖子中挑选互动较高且尚未标记已看的内容，排除“不感兴趣”。热门仅供发现参考。打开后保留原位，点击“刷新分析”再更新名单。</p></details>
    {data.items.length ? <ThreadLinks items={data.items} {...{ onSeen, seenTids }} /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本期暂无漏看精选，可查看未看帖子或切换上一周期" />}
  </>
}

function Topics({ data, onExplore, onSeen, seenTids }) {
  const { Empty } = useControls()
  return <>
    <p className="insight-note">比较标题中话题的帖子占比；每篇帖子对同一话题只计一次，至少出现于 3 篇帖子。这里只反映采集样本的变化。</p>
    {data.length ? <div className="insight-card-grid">{data.map(item => <section className="insight-topic-card" key={item.word}>
      <div className="insight-card-heading"><h3>{item.word}</h3><span className="insight-trend">+{Number(item.change_pp).toFixed(1)} 个百分点</span></div>
      <p className="insight-note">本期 {number(item.count)} 篇 · 占比 {percent(item.share)}<br />上期 {number(item.previous_count)} 篇 · 占比 {percent(item.previous_share)}</p>
      <ThreadLinks items={item.items} {...{ onSeen, seenTids }} />
      <button onClick={() => onExplore({ q: item.word })}>查看本期相关帖子</button>
    </section>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂未发现样本充足、占比上升的话题，可扩大周期查看" />}
  </>
}

function Authors({ data, onExplore, onSeen, seenTids }) {
  const { Empty } = useControls()
  return <>
    <p className="insight-note">发现本期至少有 2 篇已收录作品的作者。结合互动表现和兴趣标记提供线索，不代表内容质量评价。</p>
    {data.length ? <div className="insight-card-grid">{data.map(item => <section className="insight-topic-card" key={item.author_id}>
      <div className="insight-card-heading"><h3>{item.author || `作者 ${item.author_id}`}</h3><span>{number(item.count)} 篇</span></div>
      <p className="insight-note">{number(item.liked_count)} 篇标记感兴趣 · {number(item.hot_count)} 篇相对热门<br />回复中位数 {number(item.median_replies)}</p>
      <ThreadLinks items={item.items} {...{ onSeen, seenTids }} />
      <button onClick={() => onExplore({ authorId: item.author_id, authorName: item.author })}>查看作者本期帖子</button>
    </section>)}</div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本期暂无样本充足的作者，可扩大周期或切换板块" />}
  </>
}

function Growth({ data, onSeen, seenTids }) {
  const { Empty } = useControls()
  return <>
    <p className="insight-note">本期有记录 {number(data.tracked_count)} 篇 · 可比较 {number(data.eligible_count)} 篇</p>
    <details className="insight-explanation"><summary>增长数据怎么算？</summary><p>按本期内实际采集的两次记录比较，包含更早发布的帖子。每条显示真实观测起止时间，不代表逐日增长速度。{data.note}</p></details>
    {data.items.length ? <ThreadLinks items={data.items} {...{ onSeen, seenTids }} growth /> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={data.status === 'insufficient' ? '记录还不足。后续再次采集同一帖子后，才有真实增长可比较。' : '本期可比较的帖子暂未观测到正增长'} />}
  </>
}

export default function PeriodInsights({ data, tab, onTab, onExplore, onSeen, seenTids }) {
  const id = useId()
  function navigateTabs(event, index) {
    let next
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length
    if (event.key === 'ArrowLeft') next = (index + TABS.length - 1) % TABS.length
    if (event.key === 'Home') next = 0
    if (event.key === 'End') next = TABS.length - 1
    if (next === undefined) return
    event.preventDefault()
    onTab(TABS[next][0])
    event.currentTarget.parentElement.children[next].focus()
  }
  return <section className="period-insights insights-full" aria-label="周期数据分析">
    <div className="insight-tabs" role="tablist" aria-label="分析类型">{TABS.map(([value, label], index) => <button key={value} role="tab" id={`${id}-${value}`} aria-controls={`${id}-panel`} aria-selected={tab === value} tabIndex={tab === value ? 0 : -1} onKeyDown={event => navigateTabs(event, index)} onClick={() => onTab(value)}>{label}</button>)}</div>
    <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`} className="insight-panel" tabIndex={0}>
      {tab === 'overview' && <Overview data={data} onExplore={onExplore} onTab={onTab} />}
      {tab === 'missed' && <Missed data={data.missed} {...{ onExplore, onSeen, seenTids }} />}
      {tab === 'topics' && <Topics data={data.topics} {...{ onExplore, onSeen, seenTids }} />}
      {tab === 'authors' && <Authors data={data.authors} {...{ onExplore, onSeen, seenTids }} />}
      {tab === 'growth' && <Growth data={data.growth} {...{ onSeen, seenTids }} />}
    </div>
    <footer className="insight-footer"><span>{data.scope.note}</span><span>最近列表采集：{timeLabel(data.scope.latest_fetched_at)}</span></footer>
  </section>
}
