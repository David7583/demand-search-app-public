import { consumeNDJSON } from './streaming'
import type { StreamEvent } from './streaming'
import { allowedCredentialOrigin } from './state'
import type { CredentialBootstrap } from './state'
export type Provider = { id: string; label: string; default_base_url: string; default_api_mode: string; api_modes: string[]; notes?: string }
export type ModelConfig = { id: string; name: string; provider: string; base_url: string; api_mode: string; model: string; key_mask: string; verified_at: string; is_active: boolean }
export type ConfigList = { configs: ModelConfig[]; active_id: string | null }
export type ParseResult = { requested_model: string; actual_model: string; provider: string; connection_status: string; parsed: Record<string, unknown>; tested_at: string }
export type Validation = { validation_id: string; expires_at: string; result: ParseResult }
export type Conversation = { id: string; title: string; created_at: string; updated_at: string; message_count?: number }
export type MessageVersionReference = { id: string; number: number; status: 'draft' | 'confirmed' }
export type ChatMessage = { id: string; role: string; content: string; sequence: number; created_at: string; metadata?: { reference_version?: MessageVersionReference | null } }
export type ConversationDetail = Conversation & { messages: ChatMessage[] }
export class ApiError extends Error {
  constructor(public code: string, message: string) { super(message) }
}
let csrfToken = ''
let bootstrap: CredentialBootstrap = {}
let sessionRefresh: Promise<void> | null = null
export const isH5 = process.env.TARO_ENV === 'h5'
export function isLocalConfigurationUi(): boolean {
  return isH5 && typeof window !== 'undefined' && allowedCredentialOrigin(window.location.origin, bootstrap)
}
export async function startSession(): Promise<void> {
  if (!isH5) throw new ApiError('BACKEND_UNAVAILABLE', '微信端尚未配置可信 HTTPS 后端，请先使用本机浏览器。')
  // Share concurrent refreshes so their Set-Cookie responses cannot replace each other.
  if (!sessionRefresh) {
    sessionRefresh = (async () => {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), 10000)
      try {
        const response = await fetch('/api/v1/session', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
        if (!response.ok) throw new ApiError('SESSION_UNAVAILABLE', '本地服务尚未就绪，请使用 http://127.0.0.1:8000。')
        const data = await response.json() as CredentialBootstrap & { csrf_token?: string }
        if (!data.csrf_token) throw new ApiError('SESSION_UNAVAILABLE', '本地会话未建立，请刷新后重试。')
        csrfToken = data.csrf_token
        bootstrap = data
      } catch (error) {
        if (error instanceof ApiError) throw error
        throw new ApiError('SESSION_UNAVAILABLE', '本地会话暂时无法恢复，请确认服务已启动后重试。')
      } finally { clearTimeout(timer) }
    })().finally(() => { sessionRefresh = null })
  }
  return sessionRefresh
}
function renewWithinDeadline(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.reject(new Error('Request deadline reached'))
  return new Promise((resolve, reject) => {
    const abort = () => { reject(new Error('Request deadline reached')) }
    signal.addEventListener('abort', abort, { once: true })
    void startSession().then(resolve, reject).finally(() => signal.removeEventListener('abort', abort))
  })
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  if (!isH5 || !csrfToken) throw new ApiError('SESSION_UNAVAILABLE', '请先连接本地应用服务。')
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 65000)
  try {
    // Freeze the serialized body, including any existing idempotency ID, across recovery.
    const serialized = body === undefined ? undefined : JSON.stringify(body)
    const request = async () => {
      const token = csrfToken
      const response = await fetch('/api/v1' + path, {
        method, credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
        headers: { ...(method !== 'GET' ? { 'Content-Type': 'application/json' } : {}), ...(method !== 'GET' ? { 'X-DSA-CSRF': token } : {}) },
        body: serialized,
      })
      return { response, data: await response.json(), token }
    }
    let result = await request()
    const code = result.data.error?.code
    // Only these middleware rejections prove the operation never reached the service.
    // Provider errors, timeouts and other failures must never be automatically replayed.
    if ((result.response.status === 401 && code === 'LOCAL_SESSION_REQUIRED') ||
        (result.response.status === 403 && code === 'CSRF_REQUIRED')) {
      if (csrfToken === result.token) await renewWithinDeadline(controller.signal)
      result = await request()
    }
    if (!result.response.ok) throw new ApiError(result.data.error?.code ?? 'REQUEST_FAILED', result.data.error?.message ?? '操作失败，请重试。')
    return result.data as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('NETWORK_ERROR', '请求未完成或连接超时。配置未被替换；请检查服务状态后重试。')
  } finally { clearTimeout(timer) }
}
export function diagnosis(error: unknown): string {
  return error instanceof ApiError ? error.message + ' [' + error.code + ']' : '操作未完成，请重试。'
}
export function downloadJson(value: unknown, filename: string): void {
  if (!isH5) throw new ApiError('EXPORT_UNAVAILABLE', '当前端尚未配置文件导出方式。')
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = filename; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function collaborate<T>(path: string, body: unknown, signal: AbortSignal, onEvent: (event: StreamEvent) => void): Promise<T> {
  if (!isH5 || !csrfToken) throw new ApiError('SESSION_UNAVAILABLE', '请先连接本地应用服务。')
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal.addEventListener('abort', abort, { once: true })
  if (signal.aborted) controller.abort()
  const timer = setTimeout(abort, 90000)
  let serverError: ApiError | null = null
  try {
    const serialized = JSON.stringify(body)
    const request = () => fetch('/api/v1' + path, { method: 'POST', credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', 'X-DSA-CSRF': csrfToken, Accept: 'application/x-ndjson' }, body: serialized })
    const token = csrfToken
    let response = await request()
    if (!response.ok) {
      const data = await response.json()
      const code = data.error?.code
      if ((response.status === 401 && code === 'LOCAL_SESSION_REQUIRED') || (response.status === 403 && code === 'CSRF_REQUIRED')) {
        if (csrfToken === token) await renewWithinDeadline(controller.signal)
        response = await request()
      } else throw new ApiError(code ?? 'REQUEST_FAILED', data.error?.message ?? '对话请求失败。')
    }
    if (!response.ok) {
      const data = await response.json()
      throw new ApiError(data.error?.code ?? 'REQUEST_FAILED', data.error?.message ?? '对话请求失败。')
    }
    if (!response.body || !response.headers.get('content-type')?.includes('application/x-ndjson')) throw new ApiError('STREAM_UNSUPPORTED', '服务没有返回流式对话，未自动重试。')
    return await consumeNDJSON(response.body, event => {
      if (event.type === 'error') serverError = new ApiError(event.error.code, event.error.message)
      onEvent(event)
    }) as T
  } catch (error) {
    if (serverError) throw serverError
    if (error instanceof ApiError) throw error
    if (signal.aborted) throw new ApiError('STREAM_CANCELLED', '已停止接收。未完成内容不是保存版本；可刷新工作区核对服务端状态。')
    throw new ApiError('STREAM_INTERRUPTED', '回复未完整接收，未自动重试付费调用。请刷新版本核对是否已保存，再决定重试。')
  } finally { clearTimeout(timer); signal.removeEventListener('abort', abort); controller.abort() }
}
