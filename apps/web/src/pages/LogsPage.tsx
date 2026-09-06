import { FileText } from 'lucide-react'

import { PlannedPage } from '../components/PlannedPage'
import { usePageTitle } from '../hooks/usePageTitle'
import { currentLocale, type Locale } from '../i18n'
import { logsCatalog } from '../i18n/catalogs/logs'

export function LogsPage({ locale = currentLocale() }: { locale?: Locale }) {
  const catalog = logsCatalog.catalogs[locale]
  usePageTitle(catalog['logs.title']({}))
  return (
    <PlannedPage
      capabilities={[
        {
          title: catalog['logs.agentboxTitle']({}),
          description: catalog['logs.agentboxDescription']({}),
        },
        {
          title: catalog['logs.runtimeTitle']({}),
          description: catalog['logs.runtimeDescription']({}),
        },
        {
          title: catalog['logs.auditTitle']({}),
          description: catalog['logs.auditDescription']({}),
        },
      ]}
      copy={{
        capabilitiesAria: catalog['logs.capabilitiesAria']({}),
        notImplemented: catalog['logs.notImplemented']({}),
        planned: catalog['logs.planned']({}),
        previewOnly: catalog['logs.previewOnly']({}),
      }}
      description={catalog['logs.description']({})}
      eyebrow={catalog['logs.eyebrow']({})}
      icon={FileText}
      title={catalog['logs.title']({})}
    />
  )
}
