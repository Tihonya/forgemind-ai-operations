import type { PropsWithChildren, ReactNode } from 'react'
import { createContext, useMemo } from 'react'

export interface AuthUser {
  id: string
  username: string
  role: 'admin' | 'procurement_officer' | 'supply_analyst'
}

export interface AuthContextValue {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
}

const initialAuthContext: AuthContextValue = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
}

const AuthContext = createContext<AuthContextValue>(initialAuthContext)

export function AuthProvider({ children }: PropsWithChildren): ReactNode {
  const value = useMemo(() => initialAuthContext, [])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export { AuthContext }
