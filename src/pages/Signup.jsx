import React, { useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import AuthLayout from '../components/AuthLayout'
import { cities } from '../config/cities'
import { useAuth } from '../context/AuthContext'

export default function Signup() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    city: 'bengaluru',
    role: 'worker',
  })
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const strength = useMemo(
    () =>
      form.password.length >= 10
        ? 'Strong'
        : form.password.length >= 6
          ? 'Fair'
          : 'Weak',
    [form.password],
  )
  const update = (key, value) =>
    setForm((current) => ({ ...current, [key]: value }))
  const submit = async (event) => {
    event.preventDefault()
    setError('')
    try {
      await register({
        ...form,
        role:
          import.meta.env.VITE_DEMO_AUTH === 'true' && form.role === 'operator'
            ? 'admin'
            : form.role,
      })
      setMessage('Account created. Awaiting administrator approval.')
      setTimeout(() => navigate('/login'), 900)
    } catch (failure) {
      setError(failure.message || 'Unable to create account.')
    }
  }
  return (
    <AuthLayout>
      <h1>Create account</h1>
      <p className="muted">Request access to the AMRIN operations console.</p>
      <form onSubmit={submit}>
        <label>
          Name
          <input
            value={form.name}
            onChange={(event) => update('name', event.target.value)}
            required
            autoComplete="name"
          />
        </label>
        <label>
          Email
          <input
            type="email"
            value={form.email}
            onChange={(event) => update('email', event.target.value)}
            required
            autoComplete="email"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={form.password}
            onChange={(event) => update('password', event.target.value)}
            required
            minLength={10}
            autoComplete="new-password"
          />
          <small>
            Password strength: {strength}. Use at least 10 characters.
          </small>
        </label>
        <label>
          City
          <select
            value={form.city}
            onChange={(event) => update('city', event.target.value)}
          >
            {cities.map((city) => (
              <option key={city.id} value={city.id}>
                {city.name}
              </option>
            ))}
          </select>
        </label>
        <fieldset className="signup-role">
          <legend>Role</legend>
          <label className="signup-role-option">
            <input
              type="radio"
              name="role"
              value="worker"
              checked={form.role === 'worker'}
              onChange={() => update('role', 'worker')}
            />{' '}
            Worker
          </label>
          <label className="signup-role-option">
            <input
              type="radio"
              name="role"
              value="operator"
              checked={form.role === 'operator'}
              onChange={() => update('role', 'operator')}
            />{' '}
            Operator
          </label>
        </fieldset>
        <p className="muted">
          Accounts are approved by an admin before first sign-in.
          {import.meta.env.VITE_DEMO_AUTH !== 'true' && form.role === 'operator'
            ? ' Operator requests are provisioned as workers in this prototype.'
            : ''}
        </p>
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        {message && <p role="status">{message}</p>}
        <button className="primary">Create account</button>
      </form>
      <p className="auth-links">
        <Link to="/login">Back to sign in</Link>
      </p>
    </AuthLayout>
  )
}
