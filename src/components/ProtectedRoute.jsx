import React from 'react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function ProtectedRoute({ allowedRoles, children }) {
  const { user, ready } = useAuth()
  const location = useLocation()
  if (!ready) return null
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />
  if (allowedRoles && !allowedRoles.includes(user.role))
    return (
      <Navigate to={user.role === 'admin' ? '/admin' : '/worker'} replace />
    )
  return children || <Outlet />
}
