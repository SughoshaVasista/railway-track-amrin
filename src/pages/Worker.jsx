import React, { useEffect, useMemo, useRef, useState } from 'react'
import { divIcon } from 'leaflet'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, MapPin, Upload } from 'lucide-react'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import Header from '../components/Header'
import Lamp from '../components/Lamp'
import {
  EmptyState,
  ErrorState,
  ImageUnavailable,
  LoadingState,
  GpsUnavailable,
} from '../components/StateMessage'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useTasks } from '../hooks/useData'
import {
  apiErrorMessage,
  getTaskEvidenceImage,
  submitTaskForReview,
  updateTaskStatus,
  uploadTaskEvidence,
} from '../services/api'
import AuthenticatedImage from '../components/AuthenticatedImage'
import TaskThumbnail from '../components/TaskThumbnail'

const steps = [
  'ASSIGNED',
  'ACCEPTED',
  'IN_PROGRESS',
  'AWAITING_REVIEW',
  'COMPLETED',
]
const labels = {
  ASSIGNED: 'Assigned',
  ACCEPTED: 'Accepted',
  IN_PROGRESS: 'In Progress',
  AWAITING_REVIEW: 'Awaiting Review',
  COMPLETED: 'Finished',
}
const nextStatus = { ASSIGNED: 'ACCEPTED', ACCEPTED: 'IN_PROGRESS' }
const buttonLabel = {
  ASSIGNED: 'Accept task',
  ACCEPTED: 'Start work',
  IN_PROGRESS: 'Save repair evidence',
  AWAITING_REVIEW: 'Awaiting official review',
  COMPLETED: 'Finished by official review',
}
const display = (value) => {
  if (value === undefined || value === null || value === '') return 'NO DATA'
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value)
}

const taskPinIcon = divIcon({
  className: 'map-div-icon',
  html: `<span class="defect-marker defect-critical" style="background:#d62839;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;color:#fff;font-weight:bold;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,0.4)">!</span>`,
  iconSize: [24, 24],
  iconAnchor: [12, 12],
})

function MiniMap({ task }) {
  const gps = task.gps || {}
  const lat = Number(gps.lat ?? gps.latitude ?? task.latitude)
  const lng = Number(gps.lng ?? gps.longitude ?? task.longitude)
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return <GpsUnavailable />
  return (
    <div className="mini-map" style={{ position: 'relative' }}>
      <MapContainer
        center={[lat, lng]}
        zoom={15}
        scrollWheelZoom={true}
        dragging={true}
        tap={true}
        style={{ height: '240px', width: '100%', borderRadius: '8px' }}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution="&copy; OpenStreetMap contributors"
        />
        <Marker position={[lat, lng]} icon={taskPinIcon}>
          <Popup>
            <strong>{task.defect || 'Task Defect'}</strong>
            <br />
            {lat.toFixed(5)}, {lng.toFixed(5)}
          </Popup>
        </Marker>
      </MapContainer>
      <div style={{ marginTop: '8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <small className="mono" style={{ color: 'var(--muted)' }}>
          {lat.toFixed(5)}, {lng.toFixed(5)}
        </small>
        <Link
          to={`/map?lat=${lat}&lng=${lng}&zoom=16`}
          className="button-secondary"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '4px 10px' }}
        >
          <ExternalLink size={14} /> Open in Live Map
        </Link>
      </div>
    </div>
  )
}

function Comparison({ before, after }) {
  const [position, setPosition] = useState(50)
  if (!before && !after) return <ImageUnavailable />
  return (
    <div className={`comparison ${before && after ? 'has-both' : ''}`}>
      <div className="comparison-image comparison-after">
        {after ? <img src={after} alt="After repair" /> : <ImageUnavailable />}
      </div>
      {before && after && (
        <div className="comparison-before" style={{ width: `${position}%` }}>
          <img src={before} alt="Before repair" />
        </div>
      )}
      {before && after && (
        <input
          aria-label="Compare before and after repair"
          type="range"
          min="0"
          max="100"
          value={position}
          onChange={(event) => setPosition(event.target.value)}
        />
      )}
    </div>
  )
}

function StatusStepper({ status }) {
  const currentIndex = steps.indexOf(status)
  return (
    <div className="worker-stepper">
      {steps.map((step, index) => (
        <div
          className={`worker-step ${index <= currentIndex ? 'complete' : ''} ${step === status ? 'current' : ''}`}
          key={step}
        >
          <Lamp
            severity={index <= currentIndex ? 'clear' : 'offline'}
            label={labels[step]}
          />
        </div>
      ))}
    </div>
  )
}

function TaskDetail({
  task,
  refresh,
  uploaded,
  setUploaded,
  isAssignedWorker,
}) {
  const [file, setFile] = useState(null)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const fileInputRef = useRef(null)
  const [evidenceImages, setEvidenceImages] = useState({})
  const evidence = Array.isArray(task.evidence) ? task.evidence : []
  const evidenceKey = evidence.map((item) => item.id).join('|')
  useEffect(() => {
    let active = true
    const objectUrls = []
    Promise.all(
      evidence.map(async (item) => {
        if (!item.url) return null
        try {
          const blob = await getTaskEvidenceImage(item.url)
          const url = URL.createObjectURL(blob)
          if (!active) {
            URL.revokeObjectURL(url)
            return null
          }
          objectUrls.push(url)
          return [item.id, url]
        } catch {
          return null
        }
      }),
    ).then((items) => {
      if (active) setEvidenceImages(Object.fromEntries(items.filter(Boolean)))
    })
    return () => {
      active = false
      objectUrls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [task.id, evidenceKey])
  const status = String(task.status || 'ASSIGNED').toUpperCase()
  const canUpload = isAssignedWorker && status === 'IN_PROGRESS'
  const repairEvidence = evidence.filter((item) =>
    ['repair', 'after'].includes(item.evidence_type),
  )
  const hasCurrentRepairEvidence =
    task.review_status === 'REWORK'
      ? Boolean(
          task.review_requested_at &&
          repairEvidence.some(
            (item) =>
              new Date(item.created_at).getTime() >
              new Date(task.review_requested_at).getTime(),
          ),
        )
      : repairEvidence.length > 0
  const hasEvidenceForSubmit = uploaded || hasCurrentRepairEvidence
  const actionText = canUpload
    ? uploaded || (!file && hasCurrentRepairEvidence)
      ? 'Submit completed work for review'
      : file
        ? 'Save repair evidence'
        : 'Choose repair photo'
    : buttonLabel[status] || 'NO DATA'
  const advance = async () => {
    if (canUpload && !uploaded && !hasCurrentRepairEvidence && !file) {
      fileInputRef.current?.click()
      return
    }
    setBusy(true)
    setError('')
    try {
      if (canUpload && file && !uploaded) {
        const body = new FormData()
        body.append('file', file)
        body.append('notes', notes)
        await uploadTaskEvidence(task.id, body)
        setUploaded(true)
        setFile(null)
        return
      }
      if (canUpload && hasEvidenceForSubmit) {
        await submitTaskForReview(task.id, { notes })
        refresh?.()
        return
      }
      if (canUpload) {
        fileInputRef.current?.click()
        return
      }
      const next = nextStatus[status]
      if (next) {
        await updateTaskStatus(task.id, { status: next })
        refresh?.()
      }
    } catch (failure) {
      setError(
        apiErrorMessage(failure, 'The server did not accept this update.'),
      )
    } finally {
      setBusy(false)
    }
  }
  const rawSensors = task.sensors?.readings && typeof task.sensors.readings === 'object'
    ? task.sensors.readings
    : task.sensors
  const sensors = Array.isArray(rawSensors)
    ? rawSensors
    : rawSensors && typeof rawSensors === 'object'
      ? Object.entries(rawSensors).map(([name, item]) => {
          if (item && typeof item === 'object' && !Array.isArray(item)) {
            return {
              name,
              value: item.value ?? item.reading ?? JSON.stringify(item),
              unit: item.unit || '',
              status: item.status || 'OK',
            }
          }
          return { name, value: item }
        })
      : []
  const beforeEvidence = evidence.find(
    (item) => item.evidence_type === 'before',
  )
  const afterEvidence = [...evidence]
    .reverse()
    .find((item) => ['after', 'repair'].includes(item.evidence_type))
  const before =
    evidenceImages[beforeEvidence?.id] ||
    task.before_image ||
    task.before_image_url
  const after =
    evidenceImages[afterEvidence?.id] ||
    task.after_image ||
    task.after_image_url
  return (
    <div className="worker-detail">
      <div className="worker-detail-head">
        <Link className="back-link" to="/worker">
          <ArrowLeft size={18} />
          Assigned jobs
        </Link>
        <Lamp
          severity={String(task.priority || 'offline').toLowerCase()}
          label={task.priority || 'NO DATA'}
        />
      </div>
      <div className="worker-detail-grid">
        <section className="worker-detail-main">
          <div className="worker-image">
            {task.image_url || task.image ? (
              <AuthenticatedImage
                src={task.image_url || task.image}
                alt="Defect evidence"
              />
            ) : (
              <ImageUnavailable />
            )}
          </div>
          <section className="worker-section">
            <h2>Before / after</h2>
            <Comparison before={before} after={after} />
          </section>
          <section className="worker-section">
            <h2>Location</h2>
            <p className="data-line">
              <MapPin size={15} /> {display(task.chainage)} ·{' '}
              {display(task.track)}
            </p>
            <MiniMap task={task} />
          </section>
        </section>
        <aside className="worker-detail-side">
          <section className="worker-section">
            <p className="eyebrow">Defect</p>
            <h1>{display(task.defect || task.type)}</h1>
            <p className="data-line">{display(task.chainage)}</p>
          </section>
          <section className="worker-section">
            <h2>Status</h2>
            <StatusStepper status={status} />
            {status === 'AWAITING_REVIEW' && (
              <p className="review-notice" role="status">
                Submitted to officials. The task stays open until they approve
                it.
              </p>
            )}
            {task.review_status === 'REWORK' && (
              <div className="review-notice review-rework">
                <strong>More work requested</strong>
                <p>
                  {task.review_notes ||
                    'Review the work and add fresh repair evidence before resubmitting.'}
                </p>
              </div>
            )}
          </section>
          <section className="worker-section">
            <h2>Official review history</h2>
            {task.review_history?.length ? (
              <ol className="review-evidence-list">
                {task.review_history.map((entry, index) => (
                  <li key={`${entry.timestamp}-${index}`}>
                    <time>{entry.timestamp || 'NO DATE'}</time> · {entry.actor}{' '}
                    ·{' '}
                    {entry.action
                      .replace('maintenance_task_', '')
                      .replaceAll('_', ' ')}
                    {entry.notes ? ` — ${entry.notes}` : ''}
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState>No review decisions yet</EmptyState>
            )}
          </section>
          <section className="worker-section">
            <h2>Assigned worker</h2>
            <dl className="detail-list">
              <dt>Name</dt>
              <dd>{display(task.worker?.name)}</dd>
              <dt>Worker ID</dt>
              <dd className="mono">{display(task.worker?.worker_id)}</dd>
              <dt>City</dt>
              <dd>{display(task.worker?.city)}</dd>
            </dl>
          </section>
          <section className="worker-section">
            <h2>Sensor readout</h2>
            {sensors.length ? (
              <div className="worker-sensor-table">
                {sensors.map((sensor, index) => (
                  <div key={sensor.name || index}>
                    <span>{display(sensor.name)}</span>
                    <code>
                      {display(sensor.value)} {sensor.unit || ''}
                    </code>
                    <small>{display(sensor.status)}</small>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState>No sensor data</EmptyState>
            )}
          </section>
          <section className="worker-section">
            <h2>Notes from admin</h2>
            <p className="muted">
              {display(task.review_notes || task.admin_notes || task.notes)}
            </p>
          </section>
          {canUpload && !uploaded && (
            <section className="worker-section upload-box">
              <label className="file-button">
                <Upload size={17} />
                Upload Repair Photo
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  capture="environment"
                  onChange={(event) => setFile(event.target.files?.[0] || null)}
                />
              </label>
              {file && (
                <p className="muted" role="status">
                  Selected: {file.name}
                </p>
              )}
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Repair notes for officials"
                rows="4"
              />
              <p className="muted">
                {hasCurrentRepairEvidence
                  ? 'Repair evidence is ready. Submit it for review now or add another photo.'
                  : file
                    ? 'Photo selected. Save it to attach it to this task.'
                    : 'Choose a photo, then save it before submitting for review.'}
              </p>
            </section>
          )}
          {canUpload && uploaded && (
            <p className="review-notice" role="status">
              Repair evidence saved. Submit it when the work is ready for
              official review.
            </p>
          )}
          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}
          {isAssignedWorker && (
            <button
              className="primary worker-primary"
              disabled={
                busy || status === 'COMPLETED' || status === 'AWAITING_REVIEW'
              }
              onClick={advance}
            >
              {busy ? 'Saving evidence...' : actionText}
            </button>
          )}
        </aside>
      </div>
    </div>
  )
}

export default function Worker() {
  const { taskId } = useParams()
  const { user } = useAuth()
  const { theme, setTheme } = useTheme()
  const workerId = user?.worker_id || user?.id
  const state = useTasks(workerId)
  const [uploaded, setUploaded] = useState(false)
  useEffect(() => {
    if (!window.localStorage.getItem('amrin_theme') && theme !== 'light')
      setTheme('light')
  }, [theme, setTheme])
  const items = useMemo(() => {
    const list = Array.isArray(state.data) ? state.data : []
    return list.filter((task) => !task.worker_id || task.worker_id === workerId)
  }, [state.data, workerId])
  const critical = items.some(
    (task) => String(task.priority || task.severity).toUpperCase() === 'S3',
  )
  const task = taskId
    ? items.find((item) => String(item.id) === String(taskId))
    : null
  useEffect(() => {
    setUploaded(false)
  }, [taskId, task?.status, task?.review_status])
  if (taskId) {
    const workerKeys = [user?.id, user?.worker_id].filter(Boolean).map(String)
    const assignedKeys = [
      task?.worker_id,
      task?.worker?.id,
      task?.worker?.worker_id,
    ]
      .filter(Boolean)
      .map(String)
    const isAssignedWorker =
      user?.role === 'worker' &&
      user?.source !== 'demo' &&
      assignedKeys.some((key) => workerKeys.includes(key))
    return (
      <>
        {task ? (
          <TaskDetail
            task={task}
            refresh={state.refresh}
            uploaded={uploaded}
            setUploaded={setUploaded}
            isAssignedWorker={isAssignedWorker}
          />
        ) : state.loading ? (
          <LoadingState>Loading task...</LoadingState>
        ) : state.error ? (
          <ErrorState />
        ) : (
          <EmptyState>No maintenance tasks assigned</EmptyState>
        )}
      </>
    )
  }
  return (
    <>
      <Header
        title="Assigned jobs"
        text={`${display(user?.name)} · ${display(user?.city || 'Assigned city')}`}
      />
      {critical && (
        <div className="critical-banner">
          <Lamp severity="critical" label="S3" />
          <strong>
            Critical defect assigned. Follow the safety procedure.
          </strong>
        </div>
      )}
      <div className="worker-list">
        {state.loading ? (
          <LoadingState>Loading tasks...</LoadingState>
        ) : state.error ? (
          <ErrorState />
        ) : items.length ? (
          items.map((taskItem, index) => (
            <Link
              className={`worker-card ${index === 0 ? 'next-job' : ''}`}
              to={`/worker/${taskItem.id}`}
              key={taskItem.id}
            >
              <div className="worker-card-top">
                <Lamp
                  severity={String(
                    taskItem.priority || taskItem.severity || 'offline',
                  ).toLowerCase()}
                  label={taskItem.priority || taskItem.severity || 'NO DATA'}
                />
                <code>{display(taskItem.id)}</code>
              </div>
              <div className="worker-card-body">
                <div>
                  <p className="eyebrow">
                    {index === 0 ? 'Next job' : 'Assigned job'}
                  </p>
                  <h2>{display(taskItem.defect || taskItem.type)}</h2>
                  <p className="data-line">
                    {display(taskItem.chainage)} · {display(taskItem.track)}
                  </p>
                  <small>
                    {display(
                      taskItem.status && labels[taskItem.status]
                        ? labels[taskItem.status]
                        : taskItem.status,
                    )}
                  </small>
                  {taskItem.gps?.lat && (
                    <span className="worker-navigate">
                      <a
                        href={`https://www.google.com/maps/dir/?api=1&destination=${taskItem.gps.lat},${taskItem.gps.lng}`}
                        onClick={(event) => event.stopPropagation()}
                      >
                        Navigate
                      </a>
                    </span>
                  )}
                </div>
                <TaskThumbnail
                  taskId={taskItem.id}
                  src={
                    taskItem.thumbnail || taskItem.image_url || taskItem.image
                  }
                />
              </div>
            </Link>
          ))
        ) : (
          <EmptyState>No maintenance tasks assigned</EmptyState>
        )}
      </div>
    </>
  )
}
