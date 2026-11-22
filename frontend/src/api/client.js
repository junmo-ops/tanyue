import { siteFetch } from './site.js'
export async function requestJson(url, options = {}) {
  const isGet = (options.method || 'GET').toUpperCase() === 'GET'
  const attempts = isGet ? 2 : 1
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    const controller = new AbortController()
    const abort = () => controller.abort()
    if (options.signal?.aborted) abort()
    options.signal?.addEventListener('abort', abort, { once: true })
    let timedOut = false
    let status = 0
    const timer = isGet ? setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 30000) : null
    try {
      const response = await siteFetch(url, { ...options, signal: controller.signal })
      status = response.status
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.error || `请求失败 (${status})`)
      return payload
    } catch (error) {
      if (options.signal?.aborted) throw error
      const transient = timedOut || error instanceof TypeError || [502, 503, 504].includes(status)
      if (!isGet || !transient || attempt === attempts - 1) {
        if (timedOut) throw new Error('连接超时，请检查网络后重试', { cause: error })
        throw error
      }
    } finally {
      clearTimeout(timer)
      options.signal?.removeEventListener('abort', abort)
    }
    await new Promise(resolve => setTimeout(resolve, 500))
  }
}

export function postJson(url, body, signal) {
  return requestJson(url, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body), signal,
  })
}
