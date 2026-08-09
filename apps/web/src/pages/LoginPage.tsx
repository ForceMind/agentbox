import { FormEvent, useState } from 'react'
import { ShieldCheck } from 'lucide-react'

import { ControlPlanePulse } from '../components/ControlPlanePulse'
import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { ApiError } from '../lib/api'

export function LoginPage() {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  usePageTitle('Sign in')

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!username.trim() || !password) return
    setPending(true)
    setError(null)
    try {
      await login(username, password)
    } catch (reason) {
      setError(
        reason instanceof ApiError
          ? reason
          : new ApiError({
              code: 'CONTROL_PLANE_UNAVAILABLE',
              message: 'The control plane is unavailable',
              status: 0,
            }),
      )
    } finally {
      setPassword('')
      setPending(false)
    }
  }

  const rateLimited = error?.status === 429
  const displayError = rateLimited
    ? 'Too many failed attempts. Try again later.'
    : error?.status === 401
      ? 'Invalid credentials'
      : error?.message

  return (
    <main className="login-page">
      <section className="login-panel" aria-labelledby="login-title">
        <div className="login-brand">
          <div className="brand-mark large" aria-hidden="true">
            <ShieldCheck size={27} strokeWidth={1.8} />
          </div>
          <div>
            <p className="eyebrow">AI Developer Infrastructure</p>
            <h1>AgentBox</h1>
          </div>
        </div>

        <div className="login-copy">
          <h2 id="login-title">Sign in to manage this workstation</h2>
          <p>Use the local administrator initialized with the AgentBox CLI.</p>
        </div>

        <form
          className="login-form"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label>
            <span>Username</span>
            <input
              autoCapitalize="none"
              autoComplete="username"
              autoFocus
              maxLength={64}
              onChange={(event) => setUsername(event.target.value)}
              required
              value={username}
            />
          </label>
          <label>
            <span>Password</span>
            <input
              autoComplete="current-password"
              maxLength={1024}
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>

          {displayError && (
            <div className="login-error" role="alert">
              <strong>{displayError}</strong>
              {rateLimited && error?.retryAfter && (
                <span>
                  Try again in approximately {error.retryAfter} seconds.
                </span>
              )}
              {error?.requestId && (
                <details>
                  <summary>Request details</summary>
                  <code>{error.requestId}</code>
                </details>
              )}
            </div>
          )}

          <button
            className="primary-button"
            disabled={pending || !username.trim() || !password}
            type="submit"
          >
            {pending ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="login-footer">
          <ControlPlanePulse />
          <span>Local administrator access only</span>
        </div>
      </section>
      <aside className="login-context" aria-label="AgentBox product context">
        <p className="eyebrow">One workstation. One calm control plane.</p>
        <h2>Keep AI development infrastructure within reach.</h2>
        <p>
          AgentBox is building a secure, remote management layer for a Linux AI
          development workstation. Runtime controls arrive in later phases.
        </p>
        <ul>
          <li>Loopback-first access</li>
          <li>Server-side sessions</li>
          <li>No browser shell</li>
        </ul>
      </aside>
    </main>
  )
}
