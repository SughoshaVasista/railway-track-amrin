import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, CheckCircle, X } from 'lucide-react'
import {
  acknowledgeAlert,
  apiErrorMessage,
  assignAlert,
  changeAlertPriority,
  getAlertHistory,
  markFalsePositive,
  resolveAlert,
} from '../services/api'
import { EmptyState, ErrorState } from './StateMessage'
import SeverityBadge from './ui/SeverityBadge'
import ConfidenceChip from './ui/ConfidenceChip'
import { fusionLevel } from '../utils/fusion'
import AuthenticatedImage from './AuthenticatedImage'

const lifecycle = [
  'DETECTED',
  'VERIFIED',
  'ACKNOWLEDGED',
  'ASSIGNED',
  'UNDER_REPAIR',
  'RESOLVED',
]
const transitions = {
  DETECTED: ['VERIFIED', 'ACKNOWLEDGED', 'FALSE_POSITIVE'],
  VERIFIED: ['ACKNOWLEDGED', 'FALSE_POSITIVE'],
  ACKNOWLEDGED: ['ASSIGNED', 'FALSE_POSITIVE'],
  ASSIGNED: ['UNDER_REPAIR', 'FALSE_POSITIVE'],
  UNDER_REPAIR: ['RESOLVED', 'FALSE_POSITIVE'],
  RESOLVED: ['REOPENED'],
  FALSE_POSITIVE: ['REOPENED'],
  REOPENED: ['VERIFIED', 'ACKNOWLEDGED', 'FALSE_POSITIVE'],
}
const statusOf = (alert) =>
  String(alert?.status || 'DETECTED').toUpperCase() === 'ACTIVE'
    ? 'DETECTED'
    : String(alert?.status || 'DETECTED').toUpperCase()
const displayValue = (entry) => {
  if (entry == null || entry === '') return 'NO DATA'
  if (Array.isArray(entry)) return entry.map(displayValue).join(', ')
  if (typeof entry === 'object') {
    const reading = entry.value ?? entry.reading ?? entry.raw
    if (entry.name)
      return `${entry.name}: ${displayValue(reading ?? entry.status)}`
    if (reading !== undefined) return displayValue(reading)
    return Object.entries(entry)
      .map(([key, nested]) => `${key}: ${displayValue(nested)}`)
      .join(', ')
  }
  return String(entry)
}
const value = (item, keys) =>
  displayValue(
    keys
      .map((key) => item?.[key])
      .find((entry) => entry !== undefined && entry !== null && entry !== ''),
  )

export default function AlertDrawer({ alert, onClose, onChanged }) {
  const navigate = useNavigate()
  const [local, setLocal] = useState(alert)
  const [imageError, setImageError] = useState(false)
  const [history, setHistory] = useState(null)
  const [actionError, setActionError] = useState(null)
  const [workerId, setWorkerId] = useState('')
  const [priority, setPriority] = useState(alert?.severity || '')
  useEffect(() => {
    setLocal(alert)
    setImageError(false)
    setHistory(null)
    setActionError(null)
    setPriority(alert?.severity || '')
  }, [alert])
  if (!alert) return null
  // The drawer can render once before the selection-sync effect runs. Use the
  // selected alert immediately so opening a row never dereferences null/stale state.
  const currentAlert = local?.id === alert.id ? local : alert
  const current = statusOf(currentAlert)
  const allowed = transitions[current] || []
  const run = async (target, fn, body = {}) => {
    setActionError(null)
    try {
      const result = await fn(currentAlert.id, body)
      setLocal(result?.alert || result?.data || result)
      onChanged?.()
    } catch (error) {
      setActionError(error)
    }
  }
  const sensors = Array.isArray(currentAlert.sensors)
    ? currentAlert.sensors
    : currentAlert.sensors && typeof currentAlert.sensors === 'object'
      ? Object.entries(currentAlert.sensors).map(([name, reading]) => ({
          name,
          ...(typeof reading === 'object' ? reading : { value: reading }),
        }))
      : []
  const historyItems = Array.isArray(history)
    ? history
    : Array.isArray(history?.items)
      ? history.items
      : Array.isArray(history?.data)
        ? history.data
        : []
  const gps = currentAlert.gps || currentAlert.gps_metadata || {}
  const image = value(currentAlert, ['image_url', 'image'])
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="alert-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={`Alert ${currentAlert.id}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-head">
          <div>
            <p className="eyebrow">Alert detail</p>
            <h2>{currentAlert.id || 'NO DATA'}</h2>
          </div>
          <button
            className="icon"
            onClick={onClose}
            aria-label="Close alert detail"
          >
            <X size={18} />
          </button>
        </header>
        {actionError && (
          <ErrorState>
            {apiErrorMessage(
              actionError,
              'Action failed. Server did not accept the change.',
            )}
          </ErrorState>
        )}
        {image !== 'NO DATA' && !imageError && (
          <section className="drawer-section">
            <h3>Evidence</h3>
            <AuthenticatedImage
              className="alert-image"
              src={image}
              alt="Alert evidence"
              onError={() => setImageError(true)}
            />
          </section>
        )}
        <section className="drawer-section">
          <h3>Lifecycle</h3>
          <div className="lifecycle">
            {lifecycle.map((step) => (
              <div
                className={`lifecycle-step ${current === step ? 'current' : ''} ${lifecycle.indexOf(step) < lifecycle.indexOf(current) ? 'complete' : ''}`}
                key={step}
              >
                <i />
                {step}
              </div>
            ))}
          </div>
          {(current === 'FALSE_POSITIVE' || current === 'REOPENED') && (
            <p className="mono">{current}</p>
          )}
        </section>
        <section className="drawer-section">
          <h3>Alert data</h3>
          <div>
            <SeverityBadge severity={currentAlert.severity} />{' '}
            <ConfidenceChip value={currentAlert.confidence} />
          </div>
          <dl className="detail-list">
            <dt>Defect</dt>
            <dd>{value(currentAlert, ['defect', 'type', 'class'])}</dd>
            <dt>Track</dt>
            <dd>{value(currentAlert, ['track'])}</dd>
            <dt>Chainage</dt>
            <dd className="mono">{value(currentAlert, ['chainage'])}</dd>
            <dt>GPS</dt>
            <dd className="mono">
              {value(gps, ['lat', 'latitude'])},{' '}
              {value(gps, ['lng', 'longitude'])}
            </dd>
            <dt>Accuracy</dt>
            <dd className="mono">
              {value(gps, ['accuracy', 'accuracy_m', 'gps_accuracy'])} m
            </dd>
            <dt>Detected</dt>
            <dd>{value(currentAlert, ['detected_at', 'timestamp'])}</dd>
            <dt>Reported</dt>
            <dd>{value(currentAlert, ['created_at'])}</dd>
            <dt>City</dt>
            <dd>{value(currentAlert, ['city'])}</dd>
            <dt>Source</dt>
            <dd>{value(currentAlert, ['source'])}</dd>
            <dt>Assigned worker</dt>
            <dd>{value(currentAlert, ['assigned_worker_id'])}</dd>
          </dl>
        </section>
        <section className="drawer-section">
          <h3>Sensor evidence</h3>
          {sensors.length ? (
            <>
              <div className="sensor-table">
                {sensors.map((sensor, index) => (
                  <div className="sensor-row" key={sensor.name || index}>
                    <span>{sensor.name || 'NO DATA'}</span>
                    <code>
                      {value(sensor, ['value', 'reading'])} {sensor.unit || ''}
                    </code>
                    <small>{sensor.status || 'NO DATA'}</small>
                  </div>
                ))}
              </div>
              <p className="muted">
                Fusion confidence: <strong>{fusionLevel(sensors)}</strong>
              </p>
            </>
          ) : (
            <EmptyState>No sensor data</EmptyState>
          )}
        </section>
        <details className="action-menu">
          <summary>Actions</summary>
          <div className="action-grid">
            <button
              onClick={() =>
                document
                  .querySelector('.alert-image')
                  ?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              View evidence
            </button>
            <button
              onClick={() =>
                document
                  .querySelector('.sensor-table')
                  ?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              Sensor data
            </button>
            <button
              onClick={() =>
                document
                  .querySelector('.detail-list')
                  ?.scrollIntoView({ behavior: 'smooth' })
              }
            >
              Location
            </button>
            <button
              disabled={!allowed.includes('ACKNOWLEDGED')}
              onClick={() => run('ACKNOWLEDGED', acknowledgeAlert)}
            >
              Acknowledge
            </button>
            {current === 'ACKNOWLEDGED' && (
              <button
                className="primary"
                style={{ gridColumn: '1 / -1', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}
                onClick={() => {
                  onClose?.()
                  navigate(`/tasks?assignAlertId=${encodeURIComponent(currentAlert.id)}`)
                }}
              >
                <CheckCircle size={16} /> Assign in Tasks tab <ArrowRight size={16} />
              </button>
            )}
            <label>
              Worker ID
              <input
                value={workerId}
                onChange={(event) => setWorkerId(event.target.value)}
                placeholder="Worker ID"
              />
            </label>
            <button
              disabled={!allowed.includes('ASSIGNED') || !workerId}
              onClick={() =>
                run('ASSIGNED', assignAlert, { worker_id: workerId })
              }
            >
              Assign worker
            </button>
            <label>
              Priority
              <select
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
              >
                <option value="">NO DATA</option>
                <option value="S3">S3</option>
                <option value="S2">S2</option>
                <option value="S1">S1</option>
              </select>
            </label>
            <button
              disabled={!priority}
              onClick={() =>
                run('priority', changeAlertPriority, { severity: priority })
              }
            >
              Change priority
            </button>
            <button
              disabled={!allowed.includes('FALSE_POSITIVE')}
              onClick={() => run('FALSE_POSITIVE', markFalsePositive)}
            >
              Mark false positive
            </button>
            <button
              disabled={!allowed.includes('RESOLVED')}
              onClick={() => run('RESOLVED', resolveAlert)}
            >
              Mark resolved
            </button>
            <button
              onClick={async () => {
                try {
                  setHistory(await getAlertHistory(currentAlert.id))
                } catch (error) {
                  setActionError(error)
                }
              }}
            >
              View history
            </button>
          </div>
        </details>
        {history && (
          <section className="drawer-section">
            <h3>Audit trail</h3>
            {historyItems.length ? (
              historyItems.map((item, index) => (
                <p className="event-log-row" key={item.id || index}>
                  <time>{item.timestamp || 'NO DATA'}</time>{' '}
                  {item.action || item.status || 'NO DATA'} ·{' '}
                  {item.actor || 'SYSTEM'} {item.notes ? `· ${item.notes}` : ''}
                </p>
              ))
            ) : (
              <EmptyState>No history</EmptyState>
            )}
          </section>
        )}
      </aside>
    </div>
  )
}
