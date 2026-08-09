import { createContext, useContext } from 'react'

import { ApiClient } from '../../lib/api'
import { AuthData } from '../../lib/contracts'

export type AuthStatus = 'checking' | 'authenticated' | 'unauthenticated'

export type AuthContextValue = {
  api: ApiClient
  auth: AuthData | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  refresh: () => Promise<AuthData | null>
  status: AuthStatus
}

export const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
