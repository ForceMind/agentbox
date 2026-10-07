import { ArrowLeft, ShieldCheck } from 'lucide-react'
import { Link } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, formatMessage, type Locale } from '../i18n'
import { notFoundCatalog } from '../i18n/catalogs/notFound'
import './EntryPages.css'

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
    <main className="entry-page not-found">
      <section className="not-found-panel" aria-labelledby="not-found-title">
        <div className="not-found-brand">
          <div className="brand-mark" aria-hidden="true">
            <ShieldCheck size={22} strokeWidth={1.8} />
          </div>
          <span>{formatMessage(locale, 'app.name', {})}</span>
        </div>
        <p className="eyebrow not-found-code">404</p>
        <h1 id="not-found-title">{catalog['notFound.heading']({})}</h1>
        <p className="not-found-description">
          {catalog['notFound.description']({})}
        </p>
        <Link className="secondary-button" to={destination}>
          <ArrowLeft aria-hidden="true" size={18} />
          {status === 'authenticated'
            ? catalog['notFound.backToDashboard']({})
            : catalog['notFound.backToSignIn']({})}
        </Link>
      </section>
    </main>
  )
}
