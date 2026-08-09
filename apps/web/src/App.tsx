import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './app/AppShell'
import { ProtectedRoute, PublicOnlyRoute } from './app/RouteGuards'
import { useAuth } from './features/auth/AuthContext'
import { AuthProvider } from './features/auth/AuthProvider'
import { ClaudePage } from './pages/ClaudePage'
import { CodexPage } from './pages/CodexPage'
import { DashboardPage } from './pages/DashboardPage'
import { DoctorPage } from './pages/DoctorPage'
import { LoginPage } from './pages/LoginPage'
import { LogsPage } from './pages/LogsPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { ProjectsPage } from './pages/ProjectsPage'
import { SettingsPage } from './pages/SettingsPage'

function RootRedirect() {
  const { status } = useAuth()

  if (status === 'checking') {
    return (
      <div className="auth-boot" role="status">
        Restoring your session…
      </div>
    )
  }
  return (
    <Navigate
      replace
      to={status === 'authenticated' ? '/dashboard' : '/login'}
    />
  )
}

export function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<RootRedirect />} path="/" />
          <Route element={<PublicOnlyRoute />}>
            <Route element={<LoginPage />} path="/login" />
          </Route>
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route element={<DashboardPage />} path="/dashboard" />
              <Route element={<CodexPage />} path="/codex" />
              <Route element={<ClaudePage />} path="/claude" />
              <Route element={<ProjectsPage />} path="/projects" />
              <Route element={<DoctorPage />} path="/doctor" />
              <Route element={<LogsPage />} path="/logs" />
              <Route element={<SettingsPage />} path="/settings" />
            </Route>
          </Route>
          <Route element={<NotFoundPage />} path="*" />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}
