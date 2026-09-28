import { X } from 'lucide-react'
import { useLayoutEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

import type { WorkTab } from '../features/workbench/workTabs'
import { formatMessage, type Locale } from '../i18n'
import './WorkbenchTabs.css'

function label(locale: Locale, tab: WorkTab): string {
  const projectSuffix = tab.projectId.slice(-6)
  const kind =
    tab.kind === 'project'
      ? formatMessage(locale, 'shell.tabProject', {})
      : tab.kind === 'changes'
        ? formatMessage(locale, 'shell.tabChanges', {})
        : tab.agentType === 'codex'
          ? 'Codex'
          : 'Claude'
  return `${kind} · ${projectSuffix}`
}

export function WorkbenchTabs({
  tabs,
  activeKey,
  locale,
  onClose,
}: {
  tabs: readonly WorkTab[]
  activeKey: string | null
  locale: Locale
  onClose: (key: string) => void
}) {
  const navRef = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    const nav = navRef.current
    const active = nav?.querySelector('li.active')
    if (!nav || !active) return
    const viewport = nav.getBoundingClientRect()
    const selected = active.getBoundingClientRect()
    if (selected.right > viewport.right) {
      nav.scrollLeft += selected.right - viewport.right + 4
    } else if (selected.left < viewport.left) {
      nav.scrollLeft -= viewport.left - selected.left + 4
    }
  }, [activeKey, tabs])
  if (tabs.length === 0) return null
  return (
    <nav
      aria-label={formatMessage(locale, 'shell.openWorkTabs', {})}
      className="work-tabs"
      ref={navRef}
    >
      <ol>
        {tabs.map((tab) => {
          const tabLabel = label(locale, tab)
          return (
            <li className={tab.key === activeKey ? 'active' : ''} key={tab.key}>
              <Link
                aria-current={tab.key === activeKey ? 'page' : undefined}
                to={tab.href}
              >
                {tabLabel}
              </Link>
              <button
                aria-label={formatMessage(locale, 'shell.closeWorkTab', {
                  tab: tabLabel,
                })}
                onClick={() => onClose(tab.key)}
                type="button"
              >
                <X aria-hidden="true" size={14} />
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
