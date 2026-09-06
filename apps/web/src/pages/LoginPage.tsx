import { FormEvent, useState } from 'react'
import { ShieldCheck } from 'lucide-react'

import packageMetadata from '../../package.json'
import { ControlPlanePulse } from '../components/ControlPlanePulse'
import { LocalizedApiError, TechnicalValue } from '../components/i18n'
import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import {
  currentLocale,
  formatMessage,
  technicalApiIdentifier,
  type Locale,
} from '../i18n'
import { ApiError } from '../lib/api'

type LoginFailure = Readonly<{
  code: string
  requestId?: string
  retryAfter?: number
  status: number
}>

function normalizeLoginFailure(reason: unknown): LoginFailure {
  if (!(reason instanceof ApiError)) {
    return { code: 'CONTROL_PLANE_UNAVAILABLE', status: 0 }
  }

  const code =
    reason.status === 401
      ? 'AUTH_INVALID_CREDENTIALS'
      : reason.status === 429
        ? 'AUTH_RATE_LIMITED'
        : reason.code
  return {
    code,
    requestId: reason.requestId,
    retryAfter: reason.retryAfter,
    status: reason.status,
  }
}

export function LoginPage({
  locale = currentLocale(),
}: {
  locale?: Locale
} = {}) {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<LoginFailure | null>(null)
  usePageTitle('auth.title', {})

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!username.trim() || !password) return
    setPending(true)
    setError(null)
    try {
      await login(username, password)
    } catch (reason) {
      setError(normalizeLoginFailure(reason))
    } finally {
      setPassword('')
      setPending(false)
    }
  }

  const rateLimited = error?.status === 429
  const requestId = technicalApiIdentifier(error?.requestId)

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">
          <div className="brand-mark large" aria-hidden="true">
            <ShieldCheck size={27} strokeWidth={1.8} />
          </div>
          <div>
            <p className="eyebrow">
              {formatMessage(locale, 'auth.productCategory', {})}
            </p>
            <h1>{formatMessage(locale, 'app.name', {})}</h1>
          </div>
        </div>

        <div className="login-copy">
          <h2 id="login-title">{formatMessage(locale, 'auth.heading', {})}</h2>
          <p>{formatMessage(locale, 'auth.description', {})}</p>
        </div>

        <form
          className="login-form"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label>
            <span>{formatMessage(locale, 'auth.username', {})}</span>
            <input
              autoCapitalize="none"
              autoComplete="username"
              autoFocus
              maxLength={64}
              onChange={(event) => setUsername(event.target.value)}
              placeholder={formatMessage(
                locale,
                'auth.usernamePlaceholder',
                {},
              )}
              required
              value={username}
            />
          </label>
          <label>
            <span>{formatMessage(locale, 'auth.password', {})}</span>
            <input
              autoComplete="current-password"
              maxLength={1024}
              onChange={(event) => setPassword(event.target.value)}
              placeholder={formatMessage(
                locale,
                'auth.passwordPlaceholder',
                {},
              )}
              required
              type="password"
              value={password}
            />
          </label>

          {error && (
            <div className="login-error" role="alert">
              <strong>
                <LocalizedApiError
                  error={error}
                  locale={locale}
                  role="none"
                  showCode={false}
                  showRequestId={false}
                />
              </strong>
              {rateLimited && error.retryAfter !== undefined && (
                <span>
                  {formatMessage(locale, 'auth.retryAfter', {
                    seconds: error.retryAfter,
                  })}
                </span>
              )}
              {requestId && (
                <details>
                  <summary>
                    {formatMessage(locale, 'auth.requestDetails', {})}
                  </summary>
                  <code>
                    <TechnicalValue value={requestId.value} />
                  </code>
                </details>
              )}
            </div>
          )}

          <button
            className="primary-button"
            disabled={pending || !username.trim() || !password}
            type="submit"
          >
            {pending
              ? formatMessage(locale, 'auth.signingIn', {})
              : formatMessage(locale, 'auth.signIn', {})}
          </button>
        </form>

        <div className="login-footer">
          <ControlPlanePulse locale={locale} />
          <span>
            {formatMessage(locale, 'auth.localAdministratorOnly', {})}
          </span>
          <small className="app-version">
            {formatMessage(locale, 'auth.version', {})}{' '}
            <code>
              <TechnicalValue value={packageMetadata.version} />
            </code>
          </small>
        </div>
      </section>
      <aside
        className="login-context"
        aria-label={formatMessage(locale, 'auth.productContextLabel', {})}
      >
        <p className="eyebrow">
          {formatMessage(locale, 'auth.contextEyebrow', {})}
        </p>
        <h2>{formatMessage(locale, 'auth.contextHeading', {})}</h2>
        <p>{formatMessage(locale, 'auth.contextDescription', {})}</p>
        <ul>
          <li>{formatMessage(locale, 'auth.loopbackAccess', {})}</li>
          <li>{formatMessage(locale, 'auth.serverSessions', {})}</li>
          <li>{formatMessage(locale, 'auth.noBrowserShell', {})}</li>
        </ul>
      </aside>
    </main>
  )
}
