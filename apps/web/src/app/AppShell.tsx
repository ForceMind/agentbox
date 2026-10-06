import {
  Activity,
  Bell,
  Bot,
  Box,
  Boxes,
  FileText,
  Gauge,
  Menu,
  Search,
  Settings,
  Sparkles,
  Terminal,
  X,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'

import packageMetadata from '../../package.json'
import { ControlPlanePulse } from '../components/ControlPlanePulse'
import { OpaqueUserValue, TechnicalValue } from '../components/i18n'
import { useAuth } from '../features/auth/AuthContext'
import {
  closeWorkTab,
  openWorkTab,
  workTabForLocation,
  type WorkTab,
} from '../features/workbench/workTabs'
import { currentLocale, formatMessage, type Locale } from '../i18n'
import { CommandCenter } from './CommandCenter'
import { containDialogTab } from './dialogFocus'
import { WorkbenchTabs } from './WorkbenchTabs'

const navigation = [
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.dashboard', {}),
    path: '/dashboard',
    icon: Gauge,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.attention', {}),
    path: '/attention',
    icon: Bell,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.codex', {}),
    path: '/codex',
    icon: Bot,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.claude', {}),
    path: '/claude',
    icon: Sparkles,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.workspace', {}),
    path: '/workspace',
    icon: Terminal,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.projects', {}),
    path: '/projects',
    icon: Boxes,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.doctor', {}),
    path: '/doctor',
    icon: Activity,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.logs', {}),
    path: '/logs',
    icon: FileText,
  },
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.settings', {}),
    path: '/settings',
    icon: Settings,
  },
] as const

const navigationGroups = [
  {
    title: 'shell.workGroup',
    paths: ['/dashboard', '/attention', '/projects', '/workspace'],
  },
  { title: 'shell.agentsGroup', paths: ['/claude', '/codex'] },
  { title: 'shell.manageGroup', paths: ['/doctor', '/logs', '/settings'] },
] as const

const APP_VERSION = packageMetadata.version

function Navigation({
  locale,
  onNavigate,
}: {
  locale: Locale
  onNavigate?: () => void
}) {
  return (
    <nav
      className="primary-nav"
      aria-label={formatMessage(locale, 'shell.primaryNavigation', {})}
    >
      {navigationGroups.map((group) => (
        <div className="nav-group" key={group.title}>
          <p className="nav-group-title">
            {formatMessage(locale, group.title, {})}
          </p>
          {group.paths.map((path) => {
            const item = navigation.find((entry) => entry.path === path)!
            const Icon = item.icon
            return (
              <NavLink
                className={({ isActive }) =>
                  `nav-link${isActive ? ' active' : ''}`
                }
                key={path}
                onClick={onNavigate}
                to={path}
              >
                <Icon aria-hidden="true" size={19} strokeWidth={1.7} />
                <span>{item.label(locale)}</span>
              </NavLink>
            )
          })}
        </div>
      ))}
    </nav>
  )
}

export function AppShell({
  locale = currentLocale(),
}: {
  locale?: Locale
} = {}) {
  const { auth, logout } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const sessionId = auth?.session.id ?? null
  const routeTab = useMemo(
    () => workTabForLocation(location.pathname, location.search),
    [location.pathname, location.search],
  )
  const [workTabState, setWorkTabState] = useState<{
    sessionId: string | null
    tabs: WorkTab[]
  }>({ sessionId, tabs: [] })
  const visibleTabs =
    workTabState.sessionId === sessionId ? workTabState.tabs : []
  const [menuOpen, setMenuOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const menuDialog = useRef<HTMLDialogElement>(null)
  const menuButton = useRef<HTMLButtonElement>(null)
  const previousFocus = useRef<HTMLElement | null>(null)
  const commandActions = useMemo(
    () =>
      navigation.map(({ label, path }) => ({
        title: label(locale),
        href: path,
      })),
    [locale],
  )
  const [logoutPending, setLogoutPending] = useState(false)
  const [logoutError, setLogoutError] = useState(false)

  useEffect(() => setMenuOpen(false), [location.key, sessionId])
  useEffect(() => setCommandOpen(false), [sessionId])
  useEffect(() => setCommandOpen(false), [location.key])

  useEffect(() => {
    if (!menuOpen) return
    const dialog = menuDialog.current
    if (!dialog) return
    if (typeof dialog.showModal === 'function') dialog.showModal()
    else dialog.setAttribute('open', '')
    dialog.querySelector<HTMLButtonElement>('button')?.focus()
    const close = () => setMenuOpen(false)
    const visibility = () => {
      if (document.hidden) close()
    }
    const media = window.matchMedia?.('(min-width: 900px)')
    const resize = (event: MediaQueryListEvent) => {
      // Use this transition's value: a newer resize may already change media.matches.
      if (event.matches) close()
    }
    media?.addEventListener('change', resize)
    if (media?.matches) close()
    window.addEventListener('pagehide', close)
    window.addEventListener('offline', close)
    document.addEventListener('visibilitychange', visibility)
    return () => {
      if (typeof dialog.close === 'function' && dialog.open) dialog.close()
      else dialog.removeAttribute('open')
      media?.removeEventListener('change', resize)
      window.removeEventListener('pagehide', close)
      window.removeEventListener('offline', close)
      document.removeEventListener('visibilitychange', visibility)
    }
  }, [menuOpen])

  function closeNavigation() {
    const dialog = menuDialog.current
    if (dialog?.open && typeof dialog.close === 'function') dialog.close()
    setMenuOpen(false)
    menuButton.current?.focus()
  }

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (
        event.defaultPrevented ||
        event.isComposing ||
        event.altKey ||
        event.shiftKey ||
        !(event.metaKey || event.ctrlKey) ||
        event.key.toLowerCase() !== 'k'
      ) {
        return
      }
      event.preventDefault()
      if (commandOpen) return
      if (menuOpen) closeNavigation()
      previousFocus.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null
      setCommandOpen(true)
    }
    window.addEventListener('keydown', shortcut)
    return () => window.removeEventListener('keydown', shortcut)
  }, [commandOpen, menuOpen])

  function openCommandCenter() {
    if (menuOpen) closeNavigation()
    previousFocus.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null
    setMenuOpen(false)
    setCommandOpen(true)
  }

  function closeCommandCenter() {
    setCommandOpen(false)
    window.setTimeout(() => {
      if (previousFocus.current?.isConnected) previousFocus.current.focus()
    }, 0)
  }

  useEffect(() => {
    setWorkTabState((current) => {
      const tabs = current.sessionId === sessionId ? current.tabs : []
      return {
        sessionId,
        tabs: routeTab ? openWorkTab(tabs, routeTab) : tabs,
      }
    })
  }, [sessionId, location.key, routeTab])

  function closeTab(key: string) {
    const outcome = closeWorkTab(visibleTabs, key, routeTab?.key ?? null)
    setWorkTabState({ sessionId, tabs: outcome.tabs })
    if (outcome.nextHref) void navigate(outcome.nextHref)
  }

  async function handleLogout() {
    setLogoutPending(true)
    setLogoutError(false)
    try {
      await logout()
    } catch {
      setLogoutError(true)
    } finally {
      setLogoutPending(false)
    }
  }

  return (
    <div className="app-frame">
      <a className="skip-link" href="#main-content">
        {formatMessage(locale, 'shell.skipToContent', {})}
      </a>
      <aside className="desktop-sidebar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <Box size={21} />
          </div>
          <div>
            <strong>{formatMessage(locale, 'app.name', {})}</strong>
            <span>{formatMessage(locale, 'shell.workstation', {})}</span>
          </div>
        </div>
        <button
          className="command-center-trigger"
          onClick={openCommandCenter}
          type="button"
        >
          <Search aria-hidden="true" size={18} />
          <span>{formatMessage(locale, 'shell.commandCenter', {})}</span>
          <kbd>⌘/Ctrl K</kbd>
        </button>
        <Navigation locale={locale} />
        <div className="sidebar-footer">
          <ControlPlanePulse locale={locale} />
          <small className="app-version">
            {formatMessage(locale, 'shell.version', {})}{' '}
            <code>
              <TechnicalValue value={APP_VERSION} />
            </code>
          </small>
          <p>{formatMessage(locale, 'shell.signedInAs', {})}</p>
          {auth ? (
            <strong>
              <OpaqueUserValue value={auth.user.username} />
            </strong>
          ) : null}
          <button
            className="secondary-button"
            disabled={logoutPending}
            onClick={() => void handleLogout()}
            type="button"
          >
            {logoutPending
              ? formatMessage(locale, 'shell.signingOut', {})
              : formatMessage(locale, 'shell.signOut', {})}
          </button>
          {logoutError && (
            <p className="inline-error" role="alert">
              {formatMessage(locale, 'shell.logoutFailed', {})}
            </p>
          )}
        </div>
      </aside>

      <header className="mobile-header">
        <div className="brand-lockup compact">
          <div className="brand-mark" aria-hidden="true">
            <Box size={19} />
          </div>
          <strong>{formatMessage(locale, 'app.name', {})}</strong>
        </div>
        <div className="mobile-header-actions">
          <button
            aria-label={formatMessage(locale, 'shell.commandCenter', {})}
            className="icon-button"
            onClick={openCommandCenter}
            type="button"
          >
            <Search aria-hidden="true" />
          </button>
          <button
            ref={menuButton}
            aria-controls="mobile-navigation"
            aria-expanded={menuOpen}
            aria-label={
              menuOpen
                ? formatMessage(locale, 'shell.closeNavigation', {})
                : formatMessage(locale, 'shell.openNavigation', {})
            }
            className="icon-button"
            onClick={() => setMenuOpen((open) => !open)}
            type="button"
          >
            {menuOpen ? <X aria-hidden="true" /> : <Menu aria-hidden="true" />}
          </button>
        </div>
      </header>

      {menuOpen && (
        <dialog
          aria-label={formatMessage(locale, 'shell.primaryNavigation', {})}
          aria-modal="true"
          className="mobile-drawer"
          id="mobile-navigation"
          onKeyDown={containDialogTab}
          onCancel={(event) => {
            event.preventDefault()
            closeNavigation()
          }}
          ref={menuDialog}
        >
          <div className="mobile-drawer-heading">
            <strong>{formatMessage(locale, 'app.name', {})}</strong>
            <button
              aria-label={formatMessage(locale, 'shell.closeNavigation', {})}
              className="icon-button"
              onClick={closeNavigation}
              type="button"
            >
              <X aria-hidden="true" />
            </button>
          </div>
          <div className="mobile-drawer-meta">
            <ControlPlanePulse locale={locale} />
            {auth ? (
              <span>
                <OpaqueUserValue value={auth.user.username} />
              </span>
            ) : null}
            <small className="app-version">
              {formatMessage(locale, 'shell.version', {})}{' '}
              <code>
                <TechnicalValue value={APP_VERSION} />
              </code>
            </small>
          </div>
          <Navigation locale={locale} onNavigate={() => setMenuOpen(false)} />
          <button
            className="secondary-button mobile-logout"
            disabled={logoutPending}
            onClick={() => void handleLogout()}
            type="button"
          >
            {logoutPending
              ? formatMessage(locale, 'shell.signingOut', {})
              : formatMessage(locale, 'shell.signOut', {})}
          </button>
          {logoutError && (
            <p className="inline-error" role="alert">
              {formatMessage(locale, 'shell.logoutFailed', {})}
            </p>
          )}
        </dialog>
      )}

      <main className="app-content" id="main-content" tabIndex={-1}>
        <WorkbenchTabs
          activeKey={routeTab?.key ?? null}
          locale={locale}
          onClose={closeTab}
          tabs={visibleTabs}
        />
        <Outlet />
      </main>
      {commandOpen && sessionId && (
        <CommandCenter
          actions={commandActions}
          key={sessionId}
          locale={locale}
          onClose={closeCommandCenter}
          onNavigate={(href) => void navigate(href)}
          workspaceId={
            /^\/workspace\/(aws_[0-9a-f]{32})$/.exec(location.pathname)?.[1] ??
            null
          }
        />
      )}
    </div>
  )
}
