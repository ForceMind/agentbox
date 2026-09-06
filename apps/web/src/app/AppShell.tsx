import {
  Activity,
  Bot,
  Boxes,
  FileText,
  Gauge,
  Menu,
  Settings,
  ShieldCheck,
  Sparkles,
  Terminal,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import packageMetadata from '../../package.json'
import { ControlPlanePulse } from '../components/ControlPlanePulse'
import { OpaqueUserValue, TechnicalValue } from '../components/i18n'
import { useAuth } from '../features/auth/AuthContext'
import { currentLocale, formatMessage, type Locale } from '../i18n'

const navigation = [
  {
    label: (locale: Locale) => formatMessage(locale, 'shell.dashboard', {}),
    path: '/dashboard',
    icon: Gauge,
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
      {navigation.map(({ label, path, icon: Icon }) => (
        <NavLink
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          key={path}
          onClick={onNavigate}
          to={path}
        >
          <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
          <span>{label(locale)}</span>
        </NavLink>
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
  const [menuOpen, setMenuOpen] = useState(false)
  const [logoutPending, setLogoutPending] = useState(false)
  const [logoutError, setLogoutError] = useState(false)

  useEffect(() => setMenuOpen(false), [location.pathname])

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
      <aside className="desktop-sidebar">
        <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">
            <ShieldCheck size={21} />
          </div>
          <div>
            <strong>{formatMessage(locale, 'app.name', {})}</strong>
            <span>{formatMessage(locale, 'shell.controlPlane', {})}</span>
          </div>
        </div>
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
            <ShieldCheck size={19} />
          </div>
          <strong>{formatMessage(locale, 'app.name', {})}</strong>
        </div>
        <button
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
      </header>

      {menuOpen && (
        <div className="mobile-drawer" id="mobile-navigation">
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
        </div>
      )}

      <main className="app-content">
        <Outlet />
      </main>
    </div>
  )
}
