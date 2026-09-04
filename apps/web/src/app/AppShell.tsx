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

import { ControlPlanePulse } from '../components/ControlPlanePulse'
import { useAuth } from '../features/auth/AuthContext'
import { currentLocale, type Locale } from '../i18n'

const navigation = [
  {
    labels: { en: 'Dashboard', 'zh-CN': '概览' },
    path: '/dashboard',
    icon: Gauge,
  },
  { labels: { en: 'Codex', 'zh-CN': 'Codex' }, path: '/codex', icon: Bot },
  {
    labels: { en: 'Claude', 'zh-CN': 'Claude' },
    path: '/claude',
    icon: Sparkles,
  },
  {
    labels: { en: 'Workspace', 'zh-CN': '工作区' },
    path: '/workspace',
    icon: Terminal,
  },
  {
    labels: { en: 'Projects', 'zh-CN': '项目' },
    path: '/projects',
    icon: Boxes,
  },
  {
    labels: { en: 'Doctor', 'zh-CN': '诊断' },
    path: '/doctor',
    icon: Activity,
  },
  { labels: { en: 'Logs', 'zh-CN': '日志' }, path: '/logs', icon: FileText },
  {
    labels: { en: 'Settings', 'zh-CN': '设置' },
    path: '/settings',
    icon: Settings,
  },
] as const

const COPY = {
  en: {
    controlPlane: 'Control Plane',
    navigation: 'Primary navigation',
    signedIn: 'Signed in as',
    signingOut: 'Signing out…',
    signOut: 'Sign out',
    logoutFailed: 'Logout could not be completed',
    openNavigation: 'Open navigation',
    closeNavigation: 'Close navigation',
  },
  'zh-CN': {
    controlPlane: '控制平面',
    navigation: '主导航',
    signedIn: '当前登录用户',
    signingOut: '正在退出…',
    signOut: '退出登录',
    logoutFailed: '无法完成退出登录',
    openNavigation: '打开导航',
    closeNavigation: '关闭导航',
  },
} as const satisfies Record<Locale, Record<string, string>>

function Navigation({
  locale,
  onNavigate,
}: {
  locale: Locale
  onNavigate?: () => void
}) {
  return (
    <nav className="primary-nav" aria-label={COPY[locale].navigation}>
      {navigation.map(({ labels, path, icon: Icon }) => (
        <NavLink
          className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
          key={path}
          onClick={onNavigate}
          to={path}
        >
          <Icon aria-hidden="true" size={19} strokeWidth={1.8} />
          <span>{labels[locale]}</span>
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
  const locale = currentLocale()
  const copy = COPY[locale]

  useEffect(() => setMenuOpen(false), [location.pathname])

  async function handleLogout() {
    setLogoutPending(true)
    setLogoutError(null)
    try {
      await logout()
    } catch {
      setLogoutError(copy.logoutFailed)
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
            <span>{copy.controlPlane}</span>
          </div>
        </div>
        <Navigation locale={locale} />
        <div className="sidebar-footer">
          <ControlPlanePulse />
          <p>{copy.signedIn}</p>
          <strong>{auth?.user.username}</strong>
          <button
            className="secondary-button"
            disabled={logoutPending}
            onClick={() => void handleLogout()}
            type="button"
          >
            {logoutPending ? copy.signingOut : copy.signOut}
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
          aria-label={menuOpen ? copy.closeNavigation : copy.openNavigation}
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
          <Navigation locale={locale} onNavigate={() => setMenuOpen(false)} />
          <button
            className="secondary-button mobile-logout"
            disabled={logoutPending}
            onClick={() => void handleLogout()}
            type="button"
          >
            {logoutPending ? copy.signingOut : copy.signOut}
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
