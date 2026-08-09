import { ReactNode } from 'react'

type Tone = 'good' | 'muted' | 'warning'

export function StatusBadge({
  children,
  tone = 'muted',
}: {
  children: ReactNode
  tone?: Tone
}) {
  return <span className={`status-badge status-${tone}`}>{children}</span>
}
