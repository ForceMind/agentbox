import { LucideIcon } from 'lucide-react'

import { PageHeader } from './PageHeader'
import { StatusBadge } from './StatusBadge'

export type PlannedCapability = {
  description: string
  title: string
}

export function PlannedPage({
  capabilities,
  description,
  eyebrow,
  icon: Icon,
  title,
}: {
  capabilities: PlannedCapability[]
  description: string
  eyebrow: string
  icon: LucideIcon
  title: string
}) {
  return (
    <>
      <PageHeader description={description} eyebrow={eyebrow} title={title} />
      <section className="empty-state" aria-labelledby="planned-heading">
        <div className="empty-icon" aria-hidden="true">
          <Icon size={24} strokeWidth={1.8} />
        </div>
        <StatusBadge>Planned</StatusBadge>
        <h2 id="planned-heading">Not implemented yet</h2>
        <p>
          This section is a product preview only. It does not invoke a runtime,
          system command, or host service.
        </p>
      </section>
      <section
        className="planned-grid"
        aria-label={`Planned ${title} capabilities`}
      >
        {capabilities.map((capability) => (
          <article className="planned-card" key={capability.title}>
            <StatusBadge>Planned</StatusBadge>
            <h2>{capability.title}</h2>
            <p>{capability.description}</p>
          </article>
        ))}
      </section>
    </>
  )
}
