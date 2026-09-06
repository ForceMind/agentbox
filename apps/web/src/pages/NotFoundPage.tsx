import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, type Locale } from '../i18n'
import { notFoundCatalog } from '../i18n/catalogs/notFound'

export function NotFoundPage({
  locale = currentLocale(),
}: {
  locale?: Locale
}) {
  const { status } = useAuth()
  const catalog = notFoundCatalog.catalogs[locale]
  usePageTitle(catalog['notFound.title']({}))
  const destination = status === 'authenticated' ? '/dashboard' : '/login'

  return (
    <main className="not-found">
      <div className="brand-mark large" aria-hidden="true">
        <ShieldCheck />
      </div>
      <p className="eyebrow">404</p>
      <h1>{catalog['notFound.heading']({})}</h1>
      <p>{catalog['notFound.description']({})}</p>
      <Link className="secondary-button" to={destination}>
        <ArrowLeft aria-hidden="true" size={18} />
        {status === 'authenticated'
          ? catalog['notFound.backToDashboard']({})
          : catalog['notFound.backToSignIn']({})}
      </Link>
    </main>
  )
}
