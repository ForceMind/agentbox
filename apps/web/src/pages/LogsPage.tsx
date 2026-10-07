import { FileText, Server, ShieldCheck } from 'lucide-react'

import { PageHeader } from '../components/PageHeader'
import { StatusBadge } from '../components/StatusBadge'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, type Locale } from '../i18n'
import { logsCatalog } from '../i18n/catalogs/logs'

import './AdminPages.css'

export function LogsPage({ locale = currentLocale() }: { locale?: Locale }) {
  const catalog = logsCatalog.catalogs[locale]
  usePageTitle(catalog['logs.title']({}))
  return (
    <div className="logs-page">
      <PageHeader
        description={catalog['logs.description']({})}
        eyebrow={catalog['logs.eyebrow']({})}
        title={catalog['logs.title']({})}
      />
      <section className="empty-state" aria-labelledby="planned-heading">
        <div className="empty-icon" aria-hidden="true">
          <FileText size={28} strokeWidth={1.5} />
        </div>
        <div className="logs-preview-copy">
          <div className="logs-preview-label">
            <p className="eyebrow">{catalog['logs.previewLabel']({})}</p>
            <StatusBadge>{catalog['logs.planned']({})}</StatusBadge>
          </div>
          <h2 id="planned-heading">{catalog['logs.notImplemented']({})}</h2>
          <p>{catalog['logs.previewOnly']({})}</p>
        </div>
      </section>
      <div className="admin-group-heading">
        <h2>{catalog['logs.capabilitiesTitle']({})}</h2>
      </div>
      <section
        className="planned-grid"
        aria-label={catalog['logs.capabilitiesAria']({})}
      >
        {[
          {
            title: catalog['logs.agentboxTitle']({}),
            description: catalog['logs.agentboxDescription']({}),
            icon: FileText,
          },
          {
            title: catalog['logs.runtimeTitle']({}),
            description: catalog['logs.runtimeDescription']({}),
            icon: Server,
          },
          {
            title: catalog['logs.auditTitle']({}),
            description: catalog['logs.auditDescription']({}),
            icon: ShieldCheck,
          },
        ].map(({ title, description, icon: Icon }) => (
          <article className="planned-card" key={title}>
            <div className="logs-capability-heading">
              <span className="admin-section-icon" aria-hidden="true">
                <Icon size={21} strokeWidth={1.8} />
              </span>
              <StatusBadge>{catalog['logs.planned']({})}</StatusBadge>
            </div>
            <h2>{title}</h2>
            <p>{description}</p>
          </article>
        ))}
      </section>
    </div>
  )
}
