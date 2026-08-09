import { FormEvent, useEffect, useState } from 'react'

import { BackendStatus } from './components/BackendStatus'

type AuthData = {
  user: { id: string; username: string }
  session: { id: string; expires_at: string }
  csrf_token: string
}

type AuthEnvelope = {
  api_version: 'v1'
  request_id: string
  data: AuthData
}

type AuthState =
  | { status: 'checking' }
  | { status: 'anonymous' }
  | { status: 'authenticated'; data: AuthData }

const requestOptions = {
  credentials: 'include' as const,
  headers: { Accept: 'application/json' },
}

export function App() {
  const [auth, setAuth] = useState<AuthState>({ status: 'checking' })
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    void fetch('/api/v1/auth/me', {
      ...requestOptions,
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          setAuth({ status: 'anonymous' })
          return
        }
        const envelope = (await response.json()) as AuthEnvelope
        setAuth({ status: 'authenticated', data: envelope.data })
      })
      .catch((reason: unknown) => {
        if (!(reason instanceof DOMException && reason.name === 'AbortError')) {
          setAuth({ status: 'anonymous' })
        }
      })
    return () => controller.abort()
  }, [])

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      const response = await fetch('/api/v1/auth/login', {
        method: 'POST',
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ username, password }),
      })
      if (!response.ok) {
        setError(
          response.status === 429
            ? 'Too many attempts. Try again later.'
            : 'Invalid credentials',
        )
        return
      }
      const envelope = (await response.json()) as AuthEnvelope
      setAuth({ status: 'authenticated', data: envelope.data })
    } catch {
      setError('Control plane is unavailable')
    } finally {
      setPassword('')
      setSubmitting(false)
    }
  }

  async function logout() {
    if (auth.status !== 'authenticated') return
    setSubmitting(true)
    setError(null)
    try {
      const response = await fetch('/api/v1/auth/logout', {
        method: 'POST',
        credentials: 'include',
        headers: {
          Accept: 'application/json',
          'X-CSRF-Token': auth.data.csrf_token,
        },
      })
      if (!response.ok) {
        setError('Logout could not be completed')
        return
      }
      setAuth({ status: 'anonymous' })
    } catch {
      setError('Control plane is unavailable')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 px-5 py-10 text-slate-100 sm:px-8">
      <section className="mx-auto flex min-h-[75vh] max-w-md flex-col justify-center">
        <div className="mb-8 flex items-center justify-between gap-4">
          <p className="font-mono text-xs uppercase tracking-[0.2em] text-cyan-300">
            AI Developer Infrastructure
          </p>
          <BackendStatus />
        </div>
        <h1 className="text-5xl font-semibold tracking-tight sm:text-6xl">
          AgentBox
        </h1>

        {auth.status === 'checking' && (
          <p className="mt-8 text-slate-400" role="status">
            Checking control-plane session…
          </p>
        )}

        {auth.status === 'anonymous' && (
          <form
            className="mt-8 space-y-5 rounded-2xl border border-slate-800 bg-slate-900/70 p-6 shadow-2xl shadow-cyan-950/20"
            onSubmit={(event) => void login(event)}
          >
            <div>
              <h2 className="text-xl font-medium">Sign in</h2>
              <p className="mt-1 text-sm text-slate-400">
                Local administrator access only.
              </p>
            </div>
            <label className="block text-sm text-slate-300">
              Username
              <input
                autoComplete="username"
                className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 outline-none focus:border-cyan-400"
                maxLength={64}
                onChange={(event) => setUsername(event.target.value)}
                required
                value={username}
              />
            </label>
            <label className="block text-sm text-slate-300">
              Password
              <input
                autoComplete="current-password"
                className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2.5 outline-none focus:border-cyan-400"
                maxLength={1024}
                onChange={(event) => setPassword(event.target.value)}
                required
                type="password"
                value={password}
              />
            </label>
            {error && (
              <p className="text-sm text-rose-300" role="alert">
                {error}
              </p>
            )}
            <button
              className="w-full rounded-lg bg-cyan-300 px-4 py-2.5 font-medium text-slate-950 disabled:opacity-60"
              disabled={submitting}
              type="submit"
            >
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        )}

        {auth.status === 'authenticated' && (
          <section className="mt-8 rounded-2xl border border-emerald-900/80 bg-slate-900/70 p-6">
            <p className="font-mono text-xs uppercase tracking-[0.18em] text-emerald-300">
              Control Plane Ready
            </p>
            <h2 className="mt-3 text-xl font-medium">
              Signed in as {auth.data.user.username}
            </h2>
            <p className="mt-2 text-sm text-slate-400">
              Runtime and project controls are intentionally unavailable in
              Phase 3.
            </p>
            {error && (
              <p className="mt-4 text-sm text-rose-300" role="alert">
                {error}
              </p>
            )}
            <button
              className="mt-6 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 disabled:opacity-60"
              disabled={submitting}
              onClick={() => void logout()}
              type="button"
            >
              Logout
            </button>
          </section>
        )}
      </section>
    </main>
  )
}
