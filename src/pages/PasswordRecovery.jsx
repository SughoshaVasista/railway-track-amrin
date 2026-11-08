import React, { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { resetPassword, requestPasswordReset } from '../services/api'

export default function PasswordRecovery() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setMessage('')
    setError('')
    setBusy(true)
    try {
      if (!token) {
        await requestPasswordReset(email)
        setMessage('If an active account matches that email, reset instructions will be sent.')
      } else {
        if (password !== confirmation) throw new Error('Passwords do not match.')
        await resetPassword(token, password)
        setMessage('Password updated. You can sign in now.')
      }
    } catch (failure) {
      setError(failure.message || 'Unable to complete password reset.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="login">
      <header className="login-topbar">
        <Link className="login-brand" to="/login">RailSafe</Link>
        <p>RAILWAY CONDITION &amp; MAINTENANCE</p>
      </header>
      <div className="login-content">
        <section className="login-card">
          <p className="eyebrow">Account recovery</p>
          <h2>{token ? 'Choose a new password' : 'Forgot your password?'}</h2>
          <p className="login-subtitle">
            {token ? 'Use at least 10 characters.' : 'We will send reset instructions if an active account matches your email.'}
          </p>
          <form onSubmit={submit}>
            {!token ? (
              <label>Email<input type="email" required autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
            ) : (
              <>
                <label>New password<input type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
                <label>Confirm password<input type="password" required minLength={10} autoComplete="new-password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} /></label>
              </>
            )}
            {error && <p className="login-error" role="alert">{error}</p>}
            {message && <p role="status">{message}</p>}
            <button className="primary" type="submit" disabled={busy}>{busy ? 'Please wait…' : token ? 'Update password' : 'Send reset link'}</button>
          </form>
          <p className="auth-links"><Link to="/login">Back to sign in</Link></p>
        </section>
      </div>
    </main>
  )
}
