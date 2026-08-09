import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'

export function NotFoundPage() {
  const { status } = useAuth()
  usePageTitle('Page not found')
  const destination = status === 'authenticated' ? '/dashboard' : '/login'

  return (
    <main className="not-found">
      <div className="brand-mark large" aria-hidden="true">
        <ShieldCheck />
      </div>
      <p className="eyebrow">404</p>
      <h1>That route is not part of AgentBox.</h1>
      <p>
        The address may be outdated, or the capability may belong to a later
        phase.
      </p>
      <Link className="secondary-button" to={destination}>
        <ArrowLeft aria-hidden="true" size={18} />
        {status === 'authenticated' ? 'Back to Dashboard' : 'Back to sign in'}
      </Link>
    </main>
  )
}
