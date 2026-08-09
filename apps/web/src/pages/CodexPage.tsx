import { Bot } from 'lucide-react'

import { PlannedPage } from '../components/PlannedPage'
import { usePageTitle } from '../hooks/usePageTitle'

export function CodexPage() {
  usePageTitle('Codex')
  return (
    <PlannedPage
      capabilities={[
        {
          title: 'Remote daemon',
          description: 'Controlled start, stop, and health.',
        },
        {
          title: 'Pair new device',
          description: 'Ephemeral pair codes without persistence.',
        },
        {
          title: 'Diagnostics',
          description: 'Version and capability-aware guidance.',
        },
      ]}
      description="A future capability-aware surface for Codex standalone management."
      eyebrow="Runtime"
      icon={Bot}
      title="Codex"
    />
  )
}
