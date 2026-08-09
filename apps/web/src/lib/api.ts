type ApiErrorEnvelope = {
  error?: {
    code?: unknown
    message?: unknown
  }
  request_id?: unknown
}

type RequestOptions<T> = {
  acceptStatuses?: readonly number[]
  body?: unknown
  csrfToken?: string
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  signal?: AbortSignal
  suppressUnauthorizedRecovery?: boolean
  timeoutMs?: number
  validate?: (value: unknown) => T
}

const SAFE_REQUEST_ID = /^[A-Za-z0-9._:-]{1,72}$/

function safeText(value: unknown, fallback: string, maxLength = 256): string {
  if (typeof value !== 'string' || !value.trim()) return fallback
  const normalized = [...value]
    .filter((character) => {
      const code = character.charCodeAt(0)
      return code >= 32 && code !== 127
    })
    .join('')
    .trim()
  return normalized ? normalized.slice(0, maxLength) : fallback
}

function safeRequestId(value: unknown): string | undefined {
  return typeof value === 'string' && SAFE_REQUEST_ID.test(value)
    ? value
    : undefined
}

function parseRetryAfter(response: Response): number | undefined {
  const raw = response.headers.get('Retry-After')
  if (!raw) return undefined
  const seconds = Number.parseInt(raw, 10)
  return Number.isInteger(seconds) && seconds > 0 && seconds <= 86_400
    ? seconds
    : undefined
}

export class ApiError extends Error {
  readonly code: string
  readonly requestId?: string
  readonly retryAfter?: number
  readonly status: number

  constructor(options: {
    code: string
    message: string
    requestId?: string
    retryAfter?: number
    status: number
  }) {
    super(options.message)
    this.name = 'ApiError'
    this.code = options.code
    this.requestId = options.requestId
    this.retryAfter = options.retryAfter
    this.status = options.status
  }
}

export class ApiClient {
  constructor(private readonly onUnauthorized?: () => void) {}

  async request<T>(path: string, options: RequestOptions<T> = {}): Promise<T> {
    if (!path.startsWith('/')) throw new Error('API paths must be app-relative')
    const controller = new AbortController()
    const timeout = window.setTimeout(
      () => controller.abort(),
      options.timeoutMs ?? 10_000,
    )
    const abort = () => controller.abort()
    options.signal?.addEventListener('abort', abort, { once: true })

    const headers: Record<string, string> = { Accept: 'application/json' }
    if (options.body !== undefined) headers['Content-Type'] = 'application/json'
    if (options.csrfToken) headers['X-CSRF-Token'] = options.csrfToken

    try {
      const response = await fetch(path, {
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
        credentials: 'include',
        headers,
        method: options.method ?? 'GET',
        signal: controller.signal,
      })

      const acceptedResponse =
        response.ok ||
        (response.status !== 401 &&
          options.validate !== undefined &&
          options.acceptStatuses?.includes(response.status))
      if (!acceptedResponse) {
        let envelope: ApiErrorEnvelope = {}
        try {
          envelope = (await response.json()) as ApiErrorEnvelope
        } catch {
          // Non-JSON proxy failures use a bounded generic error below.
        }
        if (response.status === 401 && !options.suppressUnauthorizedRecovery) {
          this.onUnauthorized?.()
        }
        throw new ApiError({
          code: safeText(envelope.error?.code, `HTTP_${response.status}`, 80),
          message: safeText(
            envelope.error?.message,
            'The request could not be completed',
          ),
          requestId: safeRequestId(envelope.request_id),
          retryAfter: parseRetryAfter(response),
          status: response.status,
        })
      }

      if (response.status === 204) return undefined as T
      const payload: unknown = await response.json()
      return options.validate ? options.validate(payload) : (payload as T)
    } catch (error) {
      if (error instanceof ApiError) throw error
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError({
          code: 'REQUEST_TIMEOUT',
          message: 'The control plane did not respond in time',
          status: 0,
        })
      }
      throw new ApiError({
        code: 'CONTROL_PLANE_UNAVAILABLE',
        message: 'The control plane is unavailable',
        status: 0,
      })
    } finally {
      window.clearTimeout(timeout)
      options.signal?.removeEventListener('abort', abort)
    }
  }

  get<T>(path: string, options: Omit<RequestOptions<T>, 'method'> = {}) {
    return this.request<T>(path, { ...options, method: 'GET' })
  }

  post<T>(path: string, options: Omit<RequestOptions<T>, 'method'> = {}) {
    return this.request<T>(path, { ...options, method: 'POST' })
  }
}
