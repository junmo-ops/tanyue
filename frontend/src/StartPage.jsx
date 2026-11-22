import { useEffect, useState } from 'react'
import App from './App.jsx'
import SiteMenu from './SiteMenu.jsx'
import { requestJson } from './api/client.js'
import { siteId, siteUrl } from './api/site.js'

export default function StartPage() {
  const [sites, setSites] = useState(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    requestJson('/api/sites', {signal: controller.signal}).then(({items}) => {
      if (controller.signal.aborted) return
      if (items.length && siteId === 'default' && !items.some(item => item.id === siteId)) {
        window.location.replace(siteUrl(window.location.href, items[0].id))
      } else setSites(items)
    }).catch(e => { if (!controller.signal.aborted) setError(e.message) })
    return () => controller.abort()
  }, [])
  if (sites?.length) return <App />
  return <main className="app-shell">
    <h1>Discuz Reader</h1>
    {error ? <p role="alert">{error} <button onClick={() => window.location.reload()}>重试</button></p>
      : sites ? <><p>添加你要阅读的论坛，选择板块后即可开始同步。</p><SiteMenu first /></>
      : <p role="status">正在读取站点…</p>}
  </main>
}
