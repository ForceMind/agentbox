import { Navigate, Outlet } from 'react-router-dom'

import { useAuth } from '../features/auth/AuthContext'

function AuthBoot() {
  return (
    <main className="auth-boot" role="status">
      <span className="loading-dot" aria-hidden="true" />
      Restoring your session…
    </main>
  )
}

export function ProtectedRoute() {
  const { status } = useAuth()
  if (status === 'checking') return <AuthBoot />
  if (status === 'unauthenticated') return <Navigate replace to="/login" />
  return <Outlet />
}

export function PublicOnlyRoute() {
  const { status } = useAuth()
  if (status === 'checking') return <AuthBoot />
  if (status === 'authenticated') return <Navigate replace to="/dashboard" />
  return <Outlet />
}
