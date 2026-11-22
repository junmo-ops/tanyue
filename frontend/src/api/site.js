export const siteId = new URLSearchParams(window.location.search).get('site') || 'default'

export function siteUrl(path, id = siteId) {
  const url = new URL(path, window.location.origin)
  if (id === 'default') url.searchParams.delete('site')
  else url.searchParams.set('site', id)
  return url.pathname + url.search + url.hash
}

export function siteFetch(path, options = {}) {
  const headers = new Headers(options.headers)
  headers.set('X-Forum-Site', siteId)
  return fetch(path, { ...options, headers })
}
