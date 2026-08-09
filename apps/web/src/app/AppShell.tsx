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
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { ControlPlanePulse } from '../components/ControlPlanePulse'
import { useAuth } from '../features/auth/AuthContext'
import { ApiError } from '../lib/api'

const navigation = [
  { label: 'Dashboard', path: '/dashboard', icon: Gauge },
  { label: 'Codex', path: '/codex', icon: Bot },
  { label: 'Claude', path: '/claude', icon: Sparkles },
  { label: 'Projects', path: '/projects', icon: Boxes },
  { label: 'Doctor', path: '/doctor', icon: Activity },
  { label: 'Logs', path: '/logs', icon: FileText },
  { label: 'Settings', path: '/settings', icon: Settings },
] as const

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="primary-nav" aria-label="Primary navigation">
      {navigation.map(({ label, path, icon: Icon }) => (
        <NavLink
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          key={path}
          onClick={onNavigate}
          to={path}
        >
          <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export function AppShell() {
  const { auth, logout } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [logoutPending, setLogoutPending] = useState(false)
  const [logoutError, setLogoutError] = useState<string | null>(null)

  useEffect(() => setMenuOpen(false), [location.pathname])

  async function handleLogout() {
    setLogoutPending(true)
    setLogoutError(null)
    try {
      await logout()
    } catch (error) {
      setLogoutError(
        error instanceof ApiError
          ? error.message
          : 'Logout could not be completed',
      )
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
            <strong>AgentBox</strong>
            <span>Control Plane</span>
          </div>
        </div>
        <Navigation />
        <div className="sidebar-footer">
          <ControlPlanePulse />
          <p>Signed in as</p>
          <strong>{auth?.user.username}</strong>
          <button
            className="secondary-button"
            disabled={logoutPending}
            onClick={() => void handleLogout()}
            type="button"
          >
            {logoutPending ? 'Signing out…' : 'Sign out'}
          </button>
          {logoutError && (
            <p className="inline-error" role="alert">
              {logoutError}
            </p>
          )}
        </div>
      </aside>

      <header className="mobile-header">
        <div className="brand-lockup compact">
          <div className="brand-mark" aria-hidden="true">
            <ShieldCheck size={19} />
          </div>
          <strong>AgentBox</strong>
        </div>
        <button
          aria-controls="mobile-navigation"
          aria-expanded={menuOpen}
          aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}
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
            <ControlPlanePulse />
            <span>{auth?.user.username}</span>
          </div>
          <Navigation onNavigate={() => setMenuOpen(false)} />
          <button
            className="secondary-button mobile-logout"
            disabled={logoutPending}
            onClick={() => void handleLogout()}
            type="button"
          >
            {logoutPending ? 'Signing out…' : 'Sign out'}
          </button>
          {logoutError && (
            <p className="inline-error" role="alert">
              {logoutError}
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
