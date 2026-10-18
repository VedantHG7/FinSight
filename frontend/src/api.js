export const API = import.meta.env.VITE_API_URL || '/api'
let csrfToken = ''
export function setCsrf(token) { csrfToken = token || '' }
export async function api(path, options = {}) {
  const url = path.startsWith(API) ? path : `${API}${path}`
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (options.method && !['GET', 'HEAD'].includes(options.method)) headers.set('X-CSRF-Token', csrfToken)
  let response
  try { response = await fetch(url, { ...options, headers, credentials: 'include' }) }
  catch { throw new Error('Cannot reach FinSight. Check your connection and try again.') }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 401 && !path.includes('/auth/')) window.dispatchEvent(new Event('finsight:session-expired'))
    const detail = typeof data.detail === 'string' ? data.detail : Array.isArray(data.detail) ? data.detail.map(item => item.msg).join('. ') : null
    throw new Error(detail || (response.status >= 500 ? 'The analysis service is unavailable. Please try again shortly.' : 'Request could not be completed.'))
  }
  return data
}
