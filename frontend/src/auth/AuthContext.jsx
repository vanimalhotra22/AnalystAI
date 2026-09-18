import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getJSON, postJSON } from '../api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  // The session lives in an httpOnly cookie, so the only way to know whether we
  // are signed in is to ask the API.
  useEffect(() => {
    let alive = true
    getJSON('/auth/me')
      .then((d) => alive && setUser(d.user))
      .catch(() => alive && setUser(null))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  const signup = useCallback(async (payload) => {
    const { user: u } = await postJSON('/auth/signup', payload)
    setUser(u)
    return u
  }, [])

  const login = useCallback(async (email, password) => {
    const { user: u } = await postJSON('/auth/login', { email, password })
    setUser(u)
    return u
  }, [])

  const demoLogin = useCallback(async () => {
    const { user: u } = await postJSON('/auth/demo', {})
    setUser(u)
    return u
  }, [])

  const logout = useCallback(async () => {
    try { await postJSON('/auth/logout', {}) } finally { setUser(null) }
  }, [])

  const value = useMemo(
    () => ({ user, loading, signup, login, demoLogin, logout }),
    [user, loading, signup, login, demoLogin, logout],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
