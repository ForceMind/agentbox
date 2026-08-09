import { FileText } from 'lucide-react'

import { PlannedPage } from '../components/PlannedPage'
import { usePageTitle } from '../hooks/usePageTitle'

export function LogsPage() {
  usePageTitle('Logs')
  return (
    <PlannedPage
      capabilities={[
        {
          title: 'AgentBox logs',
          description: 'Bounded control-plane diagnostics.',
        },
        {
          title: 'Runtime logs',
          description: 'Redacted runtime-specific output.',
        },
        {
          title: 'Audit events',
          description: 'Security-relevant action history.',
        },
      ]}
      description="Application and host log viewing is not available yet."
      eyebrow="Observability"
      icon={FileText}
      title="Logs"
    />
  )
}
