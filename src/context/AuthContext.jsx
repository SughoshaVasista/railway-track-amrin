import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import {
  loginRequest,
  registerRequest,
  registerUnauthorizedHandler,
} from '../services/api'
import { loginDemo, registerDemo } from '../services/auth'

const AUTH_KEY = 'amrin_auth'
const AuthContext = createContext(null)

const normalizeAuth = (value) => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null

  // Accept the real backend response as well as the existing demo-auth format.
  const envelope =
    value.data && typeof value.data === 'object' ? value.data : value
  const user =
    envelope.user && typeof envelope.user === 'object'
      ? envelope.user
      : envelope
  const token = envelope.access_token || envelope.token
  const rawRole = String(user.role || envelope.role || '').toLowerCase()
  const role = ['admin', 'operator'].includes(rawRole)
    ? 'admin'
    : rawRole === 'worker'
      ? 'worker'
      : null
  const name = user.name || user.username || envelope.name

  if (typeof token !== 'string' || !token.trim()) return null
  if (!role || typeof name !== 'string' || !name.trim()) return null

  const rawWorkerId =
    user.worker_id ?? user.workerId ?? envelope.worker_id ?? user.id ?? null
  const rawCity = user.city ?? envelope.city ?? null
  // Backends commonly use integer IDs; keep those sessions valid across reloads.
  const workerId = rawWorkerId == null ? null : String(rawWorkerId)
  const city = rawCity == null ? null : String(rawCity)

  return {
    token: token.trim(),
    role,
    name: name.trim(),
    worker_id: workerId,
    city,
    source: String(user.source || envelope.source || 'unknown'),
  }
}

const readStoredAuth = () => {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    const raw = storage.getItem(AUTH_KEY)
    if (!raw) continue
    try {
      const value = JSON.parse(raw)
      const auth = normalizeAuth(value)
      if (auth) return auth
    } catch {
      // Discard malformed persisted auth and continue checking the other store.
    }
    storage.removeItem(AUTH_KEY)
  }
  return null
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => readStoredAuth())
  const [ready] = useState(true)

  const logout = () => {
    window.localStorage.removeItem(AUTH_KEY)
    window.sessionStorage.removeItem(AUTH_KEY)
    setAuth(null)
  }

  useEffect(() => {
    registerUnauthorizedHandler(logout)
    return () => registerUnauthorizedHandler(undefined)
  }, [])

  const login = async (credentials, remember) => {
    let result
    try {
      result = await loginRequest(credentials)
    } catch (error) {
      if (import.meta.env.VITE_DEMO_AUTH !== 'true') throw error
      result = await loginDemo(credentials.username, credentials.password)
    }
    const nextAuth = normalizeAuth(result)
    if (!nextAuth) {
      const error = new Error(
        'The server returned an invalid sign-in response. Please contact your administrator.',
      )
      error.code = 'invalid_auth_response'
      throw error
    }
    const storage = remember ? window.localStorage : window.sessionStorage
    window.localStorage.removeItem(AUTH_KEY)
    window.sessionStorage.removeItem(AUTH_KEY)
    storage.setItem(AUTH_KEY, JSON.stringify(nextAuth))
    setAuth(nextAuth)
    return nextAuth
  }

  const register = async (details) => {
    try {
      return await registerRequest(details)
    } catch (error) {
      if (import.meta.env.VITE_DEMO_AUTH !== 'true') throw error
      return registerDemo(details)
    }
  }

  const value = useMemo(
    () => ({ auth, user: auth, ready, login, register, logout }),
    [auth, ready],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => useContext(AuthContext)
