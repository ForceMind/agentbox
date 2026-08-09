import { Sparkles } from 'lucide-react'

import { PlannedPage } from '../components/PlannedPage'
import { usePageTitle } from '../hooks/usePageTitle'

export function ClaudePage() {
  usePageTitle('Claude')
  return (
    <PlannedPage
      capabilities={[
        {
          title: 'Remote sessions',
          description: 'Project-scoped session lifecycle.',
        },
        {
          title: 'Workspace Trust',
          description: 'Explicit trust guidance per workspace.',
        },
        {
          title: 'Recent output',
          description: 'Bounded, redacted session context.',
        },
      ]}
      description="A future tmux-backed home for persistent Claude Remote sessions."
      eyebrow="Runtime"
      icon={Sparkles}
      title="Claude"
    />
  )
}
