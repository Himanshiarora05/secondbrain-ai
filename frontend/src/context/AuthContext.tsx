import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { AUTH_EXPIRED_EVENT, currentUser, logIn, logOut, signUp } from '../api/client'
import type { AuthUser } from '../types'

interface AuthContextType {
  // undefined while the session is being checked at start-up; null when signed out.
  user: AuthUser | null | undefined
  login: (email: string, password: string) => Promise<void>
  signup: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null | undefined>(undefined)

  useEffect(() => {
    let active = true
    currentUser()
      .then((u) => active && setUser(u))
      .catch(() => active && setUser(null))
    // Any API call answered 401: the session expired or was logged out elsewhere.
    const onExpired = () => setUser(null)
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired)
    return () => {
      active = false
      window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired)
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    setUser(await logIn(email, password))
  }, [])

  const signup = useCallback(async (email: string, password: string) => {
    setUser(await signUp(email, password))
  }, [])

  const logout = useCallback(async () => {
    try {
      await logOut()
    } finally {
      setUser(null)
    }
  }, [])

  return <AuthContext.Provider value={{ user, login, signup, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
