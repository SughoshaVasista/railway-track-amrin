import React from 'react'
import AlertRow from '../components/AlertRow'
import MapView from '../components/MapView'
import EventLog from '../components/EventLog'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/StateMessage'
import { useAlerts, useDashboardSummary, useTasks } from '../hooks/useData'
import { useAuth } from '../context/AuthContext'
import { useCity } from '../context/CityContext'
import { cities } from '../config/cities'

export default function Dashboard() {
  const summary = useDashboardSummary()
  const alertsState = useAlerts()
  const tasksState = useTasks()
  const { user } = useAuth()
  const metrics = summary.data || {}
  const alerts = Array.isArray(alertsState.data) ? alertsState.data : []
  const tasks = Array.isArray(tasksState.data) ? tasksState.data : []
  const isDemo =
    user?.source === 'demo' ||
    metrics.demo_mode === true ||
    alerts.some((alert) => alert.demo === true || alert.source === 'demo')
  const activeAlerts = alerts.filter(
    (alert) =>
      !['RESOLVED', 'FALSE_POSITIVE'].includes(
        String(alert.status || '').toUpperCase(),
      ),
  )
  const countSeverity = (severity) =>
    activeAlerts.filter(
      (alert) =>
        String(alert.severity || alert.priority || '').toUpperCase() ===
        severity,
    ).length
  const simulatedFallback = isDemo
    ? {
        active_alerts: 3,
        s3_alerts: 1,
        s2_alerts: 1,
        s1_alerts: 1,
        pending_tasks: 3,
      }
    : {}
  const displayMetrics = {
    active_alerts:
      metrics.active_alerts ??
      (alerts.length ? activeAlerts.length : simulatedFallback.active_alerts),
    s3_alerts:
      metrics.s3_alerts ??
      (alerts.length ? countSeverity('S3') : simulatedFallback.s3_alerts),
    s2_alerts:
      metrics.s2_alerts ??
      (alerts.length ? countSeverity('S2') : simulatedFallback.s2_alerts),
    s1_alerts:
      metrics.s1_alerts ??
      (alerts.length ? countSeverity('S1') : simulatedFallback.s1_alerts),
    pending_tasks:
      metrics.pending_tasks ??
      (tasks.length
        ? tasks.filter((task) => task.status !== 'COMPLETED').length
        : simulatedFallback.pending_tasks),
    online_devices: metrics.online_devices ?? (isDemo ? 2 : undefined),
  }
  const { city } = useCity()
  const cityName = cities.find((item) => item.id === city)?.name || 'all cities'
  const s3Count = Number(displayMetrics.s3_alerts || 0)
  const kpis = [
    ['Active', displayMetrics.active_alerts, 'critical'],
    ['S3', displayMetrics.s3_alerts, 'critical'],
    ['S2', displayMetrics.s2_alerts, 'warning'],
    ['S1', displayMetrics.s1_alerts, 'minor'],
    ['Pending Repairs', displayMetrics.pending_tasks, 'warning'],
  ]
  return (
    <>
      <section className="dashboard-hero" aria-label="RailSafe overview">
        <h1>
          <span>Safer</span>
          <span>Tracks</span>
          <span>Brighter</span>
          <span>Journeys</span>
        </h1>
        <p>
          Real-time monitoring
          <br />
          for a safer tomorrow
        </p>
      </section>
      {s3Count > 0 && (
        <div className="critical-banner">
          {s3Count} active S3 alerts in {cityName}.{' '}
          <a href="/alerts?severity=S3">Review alerts</a>
        </div>
      )}
      <div className="command-grid">
        <section className="command-map" aria-label="Live track map">
          <MapView />
        </section>
        <section className="command-alerts" aria-label="Priority alerts">
          {alertsState.loading ? (
            <LoadingState>Loading alerts...</LoadingState>
          ) : alertsState.error ? (
            <ErrorState />
          ) : alerts.length ? (
            alerts
              .slice(0, 2)
              .map((alert) => <AlertRow key={alert.id} alert={alert} />)
          ) : (
            <EmptyState>No alerts</EmptyState>
          )}
        </section>
        <section className="command-kpis" aria-label="Alert summary">
          <div className="kpis">
            {kpis.map(([label, data, tone]) => (
              <article className={`kpi ${tone}`} key={label}>
                <span>{label}</span>
                <strong>{data ?? '–'}</strong>
              </article>
            ))}
          </div>
        </section>
      </div>
      <footer className="dashboard-status">
        {displayMetrics.online_devices ?? 'NO DATA'} devices online ·{' '}
        {summary.error || alertsState.error
          ? isDemo
            ? 'SIMULATED'
            : 'OFFLINE'
          : isDemo
            ? 'SIMULATED'
            : 'LIVE'}{' '}
        ·{' '}
        <time>
          {summary.updatedAt
            ? new Date(summary.updatedAt).toISOString()
            : isDemo
              ? 'DEMO DATA'
              : 'NO DATA'}
        </time>
      </footer>
      <EventLog />
    </>
  )
}
