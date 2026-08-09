import { Boxes } from 'lucide-react'

import { PlannedPage } from '../components/PlannedPage'
import { usePageTitle } from '../hooks/usePageTitle'

export function ProjectsPage() {
  usePageTitle('Projects')
  return (
    <PlannedPage
      capabilities={[
        { title: 'Create', description: 'Create a bounded project workspace.' },
        {
          title: 'Clone',
          description: 'Clone with validated URLs and ownership.',
        },
        {
          title: 'Git status',
          description: 'Read-only branch and change summaries.',
        },
      ]}
      description="Project management is not available in Phase 4."
      eyebrow="Workspaces"
      icon={Boxes}
      title="Projects"
    />
  )
}
