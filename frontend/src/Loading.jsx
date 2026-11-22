import { prefersDark } from './appearance.js'
import './Loading.css'

const posts = [
  ['91%', '49%'], ['73%'], ['86%', '62%'],
  ['78%'], ['92%', '42%'], ['66%'],
]
const tags = [68, 98, 74, 86, 60, 105, 76, 88]

export function LoadingContent({ label = '正在加载帖子', variant = 'list', rows = 6 }) {
  return <section className="ty-loading" role="status">
    <span className="ty-loading-label">{label}</span>
    {variant === 'tags' ? <div className="ty-loading-tags" aria-hidden="true">
      {tags.map(width => <span className="ty-loading-bar" key={width} style={{ width }} />)}
    </div> : <div aria-hidden="true">
      {variant === 'detail' && <div className="ty-loading-detail">
        <span className="ty-loading-bar" />
        <span className="ty-loading-bar" />
        <span className="ty-loading-bar" />
      </div>}
      {posts.slice(0, rows).map((lines, index) => <div className="ty-loading-row" key={index}>
        {lines.map(width => <span className="ty-loading-bar" key={width} style={{ width }} />)}
        <div className="ty-loading-meta"><span className="ty-loading-bar" /><span className="ty-loading-bar" /></div>
      </div>)}
    </div>}
  </section>
}

const routes = {
  '/admin': '采集管理',
  '/rankings': '排行榜',
  '/insights': '数据分析',
  '/words': '随机发现',
}

export function LoadingPage({ pathname, startup = false }) {
  const home = pathname === '/'
  const title = pathname.startsWith('/thread/') ? '帖子详情' : routes[pathname]
  return <div className={'ty-loading-page' + (startup ? ' ty-loading-startup' : '')}
    data-loading-theme={startup && prefersDark() ? 'dark' : undefined}>
    <header className="ty-loading-header">
      {title ? <span>{title}</span> : <><b aria-hidden="true">坛</b><span>坛阅</span></>}
    </header>
    {home && <div className="ty-loading-controls" aria-hidden="true">
      <div><span /><span /><span /></div>
      <div><span /><span /><span /></div>
    </div>}
    <div className="ty-loading-body">
      <LoadingContent label={title ? '正在加载' + title : '正在加载坛阅'}
        variant={pathname === '/words' ? 'tags' : pathname.startsWith('/thread/') ? 'detail' : 'list'}/>
    </div>
  </div>
}
