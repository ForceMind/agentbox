import { useEffect, useState } from 'react'

type BackendState = 'checking' | 'online' | 'unavailable'

export function BackendStatus() {
  const [state, setState] = useState<BackendState>('checking')

  useEffect(() => {
    const controller = new AbortController()

    async function checkBackend() {
      try {
        const response = await fetch('/healthz', {
          headers: { Accept: 'application/json' },
          signal: controller.signal,
        })
        setState(response.ok ? 'online' : 'unavailable')
      } catch (error) {
        if (!(error instanceof DOMException && error.name === 'AbortError')) {
          setState('unavailable')
        }
      }
    }

    void checkBackend()
    return () => controller.abort()
  }, [])

  const label = {
    checking: 'Checking',
    online: 'Online',
    unavailable: 'Unavailable',
  }[state]

  const color = {
    checking: 'bg-amber-300',
    online: 'bg-emerald-300',
    unavailable: 'bg-slate-500',
  }[state]

  return (
    <div
      aria-label={`Backend status: ${label}`}
      className="inline-flex w-fit items-center gap-2 rounded-full border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300"
    >
      <span aria-hidden="true" className={`h-2 w-2 rounded-full ${color}`} />
      Backend {label}
    </div>
  )
}
