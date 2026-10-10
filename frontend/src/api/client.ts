import { ElMessage } from 'element-plus'

/**
 * 本地 API 客户端。
 * - 令牌：桌面壳通过 ?token= 注入一次，转存 sessionStorage；SSE 走查询参数。
 * - 错误：统一 {code, message, details} 包（contracts/local-api.md），弹提示并抛 ApiError。
 */

function pickToken(): string {
  if (typeof window === 'undefined') return ''
  const url = new URL(window.location.href)
  const fromUrl = url.searchParams.get('token')
  if (fromUrl) {
    sessionStorage.setItem('saler_token', fromUrl)
    return fromUrl
  }
  return sessionStorage.getItem('saler_token') ?? ''
}

export const appToken = pickToken()

export class ApiError extends Error {
  code: string
  details: unknown

  constructor(code: string, message: string, details: unknown = null) {
    super(message)
    this.code = code
    this.details = details
  }
}

function buildQuery(params?: Record<string, unknown>): string {
  if (!params) return ''
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    qs.set(key, String(value))
  }
  const s = qs.toString()
  return s ? `?${s}` : ''
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, unknown>,
): Promise<T> {
  const resp = await fetch(`/api/v1${path}${buildQuery(params)}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      'X-App-Token': appToken,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = resp.status === 204 ? null : await resp.json().catch(() => null)
  if (!resp.ok) {
    const code = (data && data.code) || 'http_error'
    const message = (data && data.message) || `请求失败（HTTP ${resp.status}）`
    ElMessage.error(message)
    throw new ApiError(code, message, data?.details ?? null)
  }
  return data as T
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) => request<T>('GET', path, undefined, params),
  post: <T>(path: string, body?: unknown, params?: Record<string, unknown>) =>
    request<T>('POST', path, body, params),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

/** SSE（EventSource 无法带请求头，令牌走查询参数）。 */
export function sseUrl(path: string): string {
  return `/api/v1${path}${buildQuery({ token: appToken })}`
}
