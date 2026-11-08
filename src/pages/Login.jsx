import React, { useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff, LockKeyhole, TrainFront } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

export default function Login() {
  const { login } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const finish = (user) => {
    const requested = location.state?.from?.pathname
    const adminOnly = ['/alerts', '/hardware', '/ai-detection', '/tasks'].some(
      (path) => requested === path || requested?.startsWith(`${path}/`),
    )
    navigate(
      requested && (user.role === 'admin' || !adminOnly)
        ? requested
        : user.role === 'admin'
          ? '/admin'
          : '/worker',
      { replace: true },
    )
  }
  const submit = async (event) => {
    event.preventDefault()
    setError('')
    try {
      finish(await login({ username: email, password }, remember))
    } catch (failure) {
      setError(
        ['pending_approval', 'PENDING_APPROVAL'].includes(failure.code)
          ? 'Awaiting administrator approval.'
          : failure.message ||
              'Unable to sign in. Check your credentials or API connection.',
      )
    }
  }
  const demoLogin = async (role) => {
    setError('')
    try {
      finish(await login({ username: role, password: role }, false))
    } catch {
      setError(
        'Demo login unavailable. Start the mock server or use the real backend.',
      )
    }
  }
  return (
    <main className="login">
      <header className="login-topbar">
        <Link className="login-brand" to="/login">
          <span>
            <TrainFront size={22} />
          </span>
          RailSafe
        </Link>
        <p>RAILWAY CONDITION &amp; MAINTENANCE</p>
      </header>
      <div className="login-content">
        <section className="login-story">
          <p className="login-kicker">
            <span />
            REAL-TIME MONITORING FOR A SAFER TOMORROW
          </p>
          <h1>
            <span>Safer</span>
            <span>Tracks</span>
            <span>Brighter</span>
            <span>Journeys</span>
          </h1>
          <p className="login-story-copy">
            A clearer view of the railway, from track condition to the teams
            keeping every journey moving.
          </p>
          <div className="login-story-footer">
            <span>01 / 24</span>
            <i />
            <span>SAFETY IN EVERY SIGNAL</span>
          </div>
        </section>
        <section className="login-card">
          <div className="login-card-heading">
            <span className="login-lock">
              <LockKeyhole size={18} />
            </span>
            <p className="eyebrow">Secure access</p>
          </div>
          <h2>Welcome back</h2>
          <p className="login-subtitle">Sign in to your RailSafe workspace.</p>
          <form onSubmit={submit}>
            <label>
              Username
              <input
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <span className="password-input-wrap">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  required
                />
                <button
                  className="password-visibility"
                  type="button"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword((visible) => !visible)}
                >
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </span>
            </label>
            <label className="remember">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
              />
              Remember me
            </label>
            {error && (
              <p className="login-error" role="alert">
                {error}
              </p>
            )}
            <button className="primary" type="submit">
              Sign in <ArrowRight size={17} />
            </button>
          </form>
          <p className="auth-links">
            <Link to="/forgot-password">Forgot password?</Link>
            {' · '}
            <Link to="/signup">Request an account</Link>
          </p>
          {import.meta.env.VITE_DEMO_AUTH === 'true' && (
            <div className="demo-login">
              <span>DEMO ACCESS</span>
              <div>
                <button type="button" onClick={() => demoLogin('admin')}>
                  Demo Admin
                </button>
                <button type="button" onClick={() => demoLogin('worker')}>
                  Demo Worker
                </button>
              </div>
            </div>
          )}
        </section>
      </div>
      <footer className="login-footer">
        <span>RAILSAFE OPERATIONS</span>
        <span>MONITOR · INSPECT · MAINTAIN</span>
      </footer>
    </main>
  )
}
