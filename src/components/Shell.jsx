import React, { lazy, Suspense } from 'react'
import { LogOut, TrainFront, UserRound } from 'lucide-react'
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router-dom'
import Nav from './Nav'
import ProtectedRoute from './ProtectedRoute'
import { useAuth } from '../context/AuthContext'
import { LoadingState } from './StateMessage'
import ThemeToggle from './ui/ThemeToggle'
import CityFilter from './CityFilter'
import { useAlerts } from '../hooks/useData'

const Dashboard = lazy(() => import('../pages/Dashboard'))
const Alerts = lazy(() => import('../pages/Alerts'))
const MapPage = lazy(() => import('../pages/MapPage'))
const Hardware = lazy(() => import('../pages/Hardware'))
const ModelDemo = lazy(() => import('../pages/ModelDemo'))
const Worker = lazy(() => import('../pages/Worker'))
const Tasks = lazy(() => import('../pages/Tasks'))

export default function Shell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const alerts = useAlerts()
  if (!user) return null
  const home = user.role === 'admin' ? '/admin' : '/worker'
  const admin = (element) => (
    <ProtectedRoute allowedRoles={['admin']}>{element}</ProtectedRoute>
  )
  const s3 = (Array.isArray(alerts.data) ? alerts.data : []).filter(
    (item) => item.severity === 'S3' && item.status !== 'RESOLVED',
  ).length
  const search = (event) => {
    event.preventDefault()
    const query = event.currentTarget.elements.q.value.trim()
    navigate(`/alerts${query ? `?q=${encodeURIComponent(query)}` : ''}`)
  }
  return (
    <div className="shell">
      <Nav />
      <header className="topbar">
        <div className="topbar-brand">
          <TrainFront size={22} />
          <b>AMRIN</b>
        </div>
        {user.role === 'admin' && <CityFilter />}
        {user.source === 'demo' && (
          <span className="demo-mode-chip">DEMO DATA · SIMULATED</span>
        )}
        <form className="topbar-search" onSubmit={search}>
          <input
            name="q"
            aria-label="Search alerts"
            placeholder="Search alerts"
            defaultValue={new URLSearchParams(location.search).get('q') || ''}
          />
        </form>
        <div className="topbar-user">
          <ThemeToggle />
          {s3 > 0 && (
            <button
              className="s3-link"
              onClick={() => navigate('/alerts?severity=S3')}
            >
              S3 {s3}
            </button>
          )}
          <UserRound size={16} />
          <span>{user.name}</span>
          <button className="icon" onClick={logout} aria-label="Log out">
            <LogOut size={17} />
          </button>
        </div>
      </header>
      <main className="content">
        <div className="page">
          {user.source === 'demo' && (
            <div className="demo-data-banner" role="status">
              <strong>DEMO DATA</strong>
              <span>
                Sample records and simulated sensor readings. No live hardware
                data.
              </span>
            </div>
          )}
          <Suspense fallback={<LoadingState>Loading view...</LoadingState>}>
            <Routes>
              <Route path="/" element={<Navigate to={home} replace />} />
              <Route path="/admin" element={admin(<Dashboard />)} />
              <Route path="/alerts" element={admin(<Alerts />)} />
              <Route path="/hardware" element={admin(<Hardware />)} />
              <Route path="/model-demo" element={admin(<ModelDemo />)} />
              <Route path="/tasks" element={admin(<Tasks />)} />
              <Route
                path="/map"
                element={
                  <ProtectedRoute allowedRoles={['admin', 'worker']}>
                    <MapPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/ai-detection"
                element={<Navigate to="/alerts" replace />}
              />
              <Route
                path="/repair-history"
                element={<Navigate to="/alerts?tab=resolved" replace />}
              />
              <Route
                path="/workers"
                element={<Navigate to="/tasks?tab=workers" replace />}
              />
              <Route
                path="/sensor-history"
                element={<Navigate to="/hardware?tab=history" replace />}
              />
              <Route
                path="/model"
                element={<Navigate to="/hardware?tab=model" replace />}
              />
              <Route
                path="/switching"
                element={<Navigate to="/simulation/simulator" replace />}
              />
              <Route
                path="/settings"
                element={<Navigate to="/admin" replace />}
              />
              <Route
                path="/worker"
                element={
                  <ProtectedRoute allowedRoles={['admin', 'worker']}>
                    <Worker />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/worker/:taskId"
                element={
                  <ProtectedRoute allowedRoles={['admin', 'worker']}>
                    <Worker />
                  </ProtectedRoute>
                }
              />
              <Route path="*" element={<Navigate to={home} replace />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  )
}
