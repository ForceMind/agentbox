import { LucideIcon } from 'lucide-react'

import { PageHeader } from './PageHeader'
import { StatusBadge } from './StatusBadge'

export type PlannedCapability = {
  description: string
  title: string
}

export type PlannedPageCopy = {
  capabilitiesAria: string
  notImplemented: string
  planned: string
  previewOnly: string
}

export function PlannedPage({
  capabilities,
  copy,
  description,
  eyebrow,
  icon: Icon,
  title,
}: {
  capabilities: PlannedCapability[]
  copy: PlannedPageCopy
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
        <StatusBadge>{copy.planned}</StatusBadge>
        <h2 id="planned-heading">{copy.notImplemented}</h2>
        <p>{copy.previewOnly}</p>
      </section>
      <section className="planned-grid" aria-label={copy.capabilitiesAria}>
        {capabilities.map((capability) => (
          <article className="planned-card" key={capability.title}>
            <StatusBadge>{copy.planned}</StatusBadge>
            <h2>{capability.title}</h2>
            <p>{capability.description}</p>
          </article>
        ))}
      </section>
    </>
  )
}
