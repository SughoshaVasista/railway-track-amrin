import React, { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Header from '../components/Header'
import Drawer from '../components/Drawer'
import Lamp from '../components/Lamp'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/StateMessage'
import { useAuth } from '../context/AuthContext'
import {
  useAlerts,
  usePendingUsers,
  useTasks,
  useWorkers,
} from '../hooks/useData'
import {
  apiErrorMessage,
  approveUser,
  assignTask,
  createTask,
  getTaskEvidenceImage,
  rejectUser,
  reviewTask,
  unassignTask,
} from '../services/api'

function ReviewEvidence({ items = [] }) {
  const [images, setImages] = useState({})
  const evidenceKey = items.map((item) => item.id).join('|')
  useEffect(() => {
    let active = true
    const urls = []
    Promise.all(
      items.map(async (item) => {
        if (!item.url) return null
        try {
          const blob = await getTaskEvidenceImage(item.url)
          const url = URL.createObjectURL(blob)
          if (!active) {
            URL.revokeObjectURL(url)
            return null
          }
          urls.push(url)
          return [item.id, url]
        } catch {
          return null
        }
      }),
    ).then((results) => {
      if (active) setImages(Object.fromEntries(results.filter(Boolean)))
    })
    return () => {
      active = false
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [evidenceKey])
  return items.length ? (
    <div className="review-evidence-gallery">
      {items.map((item) => (
        <figure key={item.id}>
          <figcaption>
            {item.evidence_type} · {item.original_filename || 'Photo evidence'}{' '}
            · {item.created_at || 'NO DATE'}
          </figcaption>
          {images[item.id] ? (
            <img
              src={images[item.id]}
              alt={`${item.evidence_type} task evidence`}
            />
          ) : (
            <p className="muted">Loading evidence preview…</p>
          )}
        </figure>
      ))}
    </div>
  ) : (
    <p className="muted">No evidence submitted.</p>
  )
}

export default function Tasks() {
  const { user } = useAuth()
  const isDemo = user?.source === 'demo'
  const canReviewTasks = user?.role === 'admin' && !isDemo
  const [searchParams, setSearchParams] = useSearchParams()
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState(false)
  const [alertId, setAlertId] = useState('')
  const [workerId, setWorkerId] = useState('')
  const [submitError, setSubmitError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState('')
  const [busyUserId, setBusyUserId] = useState('')
  const [busyTaskId, setBusyTaskId] = useState('')
  const [taskWorkers, setTaskWorkers] = useState({})
  const [selectedTask, setSelectedTask] = useState(null)
  const [reviewNotes, setReviewNotes] = useState('')
  const [reviewBusy, setReviewBusy] = useState(false)
  const [reviewError, setReviewError] = useState('')
  const tasksState = useTasks()
  const alertsState = useAlerts()
  const workersState = useWorkers()
  const pendingState = usePendingUsers()
  const allTasks = Array.isArray(tasksState.data) ? tasksState.data : []
  const tasks = allTasks.filter((task) => !status || task.status === status)
  const openTaskAlertIds = new Set(
    allTasks
      .filter((task) => task.status !== 'COMPLETED')
      .map((task) => task.alert_id),
  )
  const eligibleAlerts = (
    Array.isArray(alertsState.data) ? alertsState.data : []
  ).filter(
    (alert) =>
      ['ACKNOWLEDGED', 'ASSIGNED'].includes(
        String(alert.status).toUpperCase(),
      ) && !openTaskAlertIds.has(alert.id),
  )
  const allWorkers = Array.isArray(workersState.data) ? workersState.data : []
  const pendingUsers = Array.isArray(pendingState.data) ? pendingState.data : []

  // Check URL query parameters for pre-selected alert to assign
  useEffect(() => {
    const targetAlertId = searchParams.get('assignAlertId')
    if (targetAlertId) {
      setAlertId(targetAlertId)
      setOpen(true)
      const nextParams = new URLSearchParams(searchParams)
      nextParams.delete('assignAlertId')
      setSearchParams(nextParams, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // Get selected alert object to determine its city/area
  const selectedAlert = useMemo(
    () => eligibleAlerts.find((item) => item.id === alertId),
    [eligibleAlerts, alertId],
  )

  // Filter workers located in the same city/area as the alert (or show all if city is undefined or matches)
  const workers = useMemo(() => {
    const alertCity = (selectedAlert?.city || '').toLowerCase().trim()
    if (!alertCity) return allWorkers
    const matched = allWorkers.filter(
      (w) => (w.city || '').toLowerCase().trim() === alertCity,
    )
    return matched.length ? matched : allWorkers
  }, [allWorkers, selectedAlert])

  const submit = async (event) => {
    event.preventDefault()
    setMessage('')
    setSubmitError('')
    setSubmitting(true)
    try {
      await createTask({
        alert_id: alertId,
        worker_id: workerId,
        status: 'ASSIGNED',
      })
      setMessage('Task created.')
      setOpen(false)
      setAlertId('')
      setWorkerId('')
      setSubmitError('')
      tasksState.refresh()
      alertsState.refresh()
    } catch (error) {
      const messages = {
        invalid_alert_transition:
          'Acknowledge this alert first, then create its task.',
        open_task_exists:
          'This alert already has an open task. Choose another alert.',
        worker_not_found:
          'That worker is no longer active. Choose an approved worker.',
      }
      setSubmitError(
        messages[error?.code] ||
          apiErrorMessage(error, 'Task creation failed.'),
      )
    } finally {
      setSubmitting(false)
    }
  }

  const decideSignup = async (user, action) => {
    setBusyUserId(user.id)
    setMessage('')
    try {
      if (action === 'approve') await approveUser(user.id)
      else await rejectUser(user.id)
      setMessage(
        action === 'approve'
          ? `${user.name} approved as a worker.`
          : `${user.name} rejected.`,
      )
      pendingState.refresh()
      workersState.refresh()
    } catch (error) {
      setMessage(apiErrorMessage(error, 'The account decision was not saved.'))
    } finally {
      setBusyUserId('')
    }
  }

  const updateAssignment = async (task, action) => {
    setBusyTaskId(task.id)
    setMessage('')
    try {
      if (action === 'unassign') {
        await unassignTask(task.id)
        setMessage(`${task.id} is now unassigned.`)
        setTaskWorkers((current) => ({ ...current, [task.id]: '' }))
      } else {
        const workerId = taskWorkers[task.id]
        if (!workerId) return
        await assignTask(task.id, { worker_id: workerId })
        setMessage(`${task.id} assignment updated.`)
      }
      tasksState.refresh()
      alertsState.refresh()
    } catch (error) {
      setMessage(
        apiErrorMessage(error, 'Task assignment could not be updated.'),
      )
    } finally {
      setBusyTaskId('')
    }
  }

  const decideTaskReview = async (decision) => {
    if (!selectedTask || !canReviewTasks) return
    setReviewBusy(true)
    setReviewError('')
    try {
      await reviewTask(selectedTask.id, { decision, notes: reviewNotes })
      setMessage(
        decision === 'approve'
          ? `${selectedTask.id} approved as finished.`
          : `${selectedTask.id} returned to the worker for more work.`,
      )
      setSelectedTask(null)
      setReviewNotes('')
      tasksState.refresh()
      alertsState.refresh()
    } catch (error) {
      setReviewError(
        apiErrorMessage(error, 'The review decision could not be saved.'),
      )
    } finally {
      setReviewBusy(false)
    }
  }

  return (
    <>
      <Header title="Tasks" text="Assign and monitor maintenance work." />
      {isDemo && (
        <p className="muted">
          Assign sample tasks to the demo worker. Account approvals and other
          record changes are disabled.
        </p>
      )}
      <section
        className="panel pending-approvals"
        aria-labelledby="pending-approvals-title"
      >
        <div className="panel-head">
          <h2 id="pending-approvals-title">Signup approvals</h2>
          <span>
            {pendingState.loading
              ? 'Loading'
              : `${pendingUsers.length} pending`}
          </span>
        </div>
        {pendingState.loading ? (
          <LoadingState>Loading signup requests...</LoadingState>
        ) : pendingState.error ? (
          <ErrorState>Unable to load pending accounts.</ErrorState>
        ) : pendingUsers.length ? (
          <div className="admin-list">
            {pendingUsers.map((user) => (
              <article className="admin-row pending-user-row" key={user.id}>
                <div>
                  <b>{user.name}</b>
                  <small className="data-line">
                    {user.email} · {user.city || 'City not set'}
                  </small>
                </div>
                <div className="pending-user-actions">
                  <button
                    type="button"
                    disabled={isDemo || Boolean(busyUserId)}
                    onClick={() => decideSignup(user, 'approve')}
                  >
                    {busyUserId === user.id ? 'Saving...' : 'Approve worker'}
                  </button>
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={isDemo || Boolean(busyUserId)}
                    onClick={() => decideSignup(user, 'reject')}
                  >
                    Reject
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState>No pending signup requests</EmptyState>
        )}
      </section>

      <div className="toolbar-row">
        <label>
          Status
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">ALL</option>
            <option>ASSIGNED</option>
            <option>ACCEPTED</option>
            <option>IN_PROGRESS</option>
            <option>AWAITING_REVIEW</option>
            <option>COMPLETED</option>
          </select>
        </label>
        {!isDemo && (
          <button
            className="primary"
            onClick={() => {
              setMessage('')
              setSubmitError('')
              setOpen(true)
            }}
          >
            Assign Worker
          </button>
        )}
      </div>
      {message && (
        <p className="muted" role="status">
          {message}
        </p>
      )}
      {tasksState.loading ? (
        <LoadingState>Loading tasks...</LoadingState>
      ) : tasksState.error ? (
        <ErrorState />
      ) : tasks.length ? (
        <div className="admin-list">
          {tasks.map((task) => (
            <article className="admin-row task-admin-row" key={task.id}>
              <Lamp
                severity={String(
                  task.priority || task.severity || 'missing_data',
                ).toLowerCase()}
                label={task.priority || task.severity || 'NO DATA'}
              />
              <div className="task-admin-summary">
                <b>{task.defect || task.type || 'NO DATA'}</b>
                <small className="data-line">
                  {task.chainage || 'NO DATA'} ·{' '}
                  <button
                    type="button"
                    className="worker-task-trigger"
                    onClick={() => {
                      setSelectedTask(task)
                      setReviewNotes('')
                    }}
                  >
                    {task.worker?.name ||
                      task.worker_id ||
                      'Awaiting worker assignment'}
                  </button>
                </small>
              </div>
              <code>
                {task.status === 'ASSIGNED' && !task.worker_id
                  ? 'AWAITING ASSIGNMENT'
                  : task.status === 'AWAITING_REVIEW'
                    ? 'AWAITING REVIEW'
                    : task.status || 'NO DATA'}
              </code>
              {task.status === 'ASSIGNED' && task.worker_id ? (
                <button
                  type="button"
                  className="button-secondary task-assignment-action"
                  disabled={Boolean(busyTaskId)}
                  onClick={() => updateAssignment(task, 'unassign')}
                >
                  {busyTaskId === task.id ? 'Saving...' : 'Unassign'}
                </button>
              ) : task.status === 'ASSIGNED' ? (
                <div className="task-reassign">
                  <select
                    aria-label={`Assign ${task.id} to worker`}
                    value={taskWorkers[task.id] || ''}
                    onChange={(event) =>
                      setTaskWorkers((current) => ({
                        ...current,
                        [task.id]: event.target.value,
                      }))
                    }
                  >
                    <option value="">Select worker</option>
                    {workers.map((worker) => (
                      <option
                        key={worker.id || worker.worker_id}
                        value={worker.id || worker.worker_id}
                      >
                        {worker.name || worker.id || 'NO DATA'}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="button-secondary"
                    disabled={!taskWorkers[task.id] || Boolean(busyTaskId)}
                    onClick={() => updateAssignment(task, 'assign')}
                  >
                    {busyTaskId === task.id ? 'Saving...' : 'Assign'}
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  className="button-secondary task-assignment-action"
                  onClick={() => {
                    setSelectedTask(task)
                    setReviewNotes('')
                  }}
                >
                  {task.status === 'AWAITING_REVIEW' ? 'Review' : 'Details'}
                </button>
              )}
            </article>
          ))}
        </div>
      ) : (
        <EmptyState>No tasks</EmptyState>
      )}
      <Drawer
        open={open}
        title="Assign Worker"
        onClose={() => {
          setOpen(false)
          setSubmitError('')
        }}
      >
        <form className="drawer-form" onSubmit={submit}>
          <label>
            Acknowledged alert
            <select
              required
              value={alertId}
              onChange={(event) => {
                setAlertId(event.target.value)
                setSubmitError('')
              }}
            >
              <option value="">Select alert</option>
              {eligibleAlerts.map((alert) => (
                <option key={alert.id} value={alert.id}>
                  {alert.id} · {alert.defect || 'NO DATA'}
                </option>
              ))}
            </select>
          </label>
          {eligibleAlerts.length === 0 && (
            <p className="muted" role="status">
              No acknowledged alerts are available. Acknowledge an alert first,
              or finish its existing task.
            </p>
          )}
          <label>
            Worker {selectedAlert?.city ? `(Filtered for ${selectedAlert.city})` : ''}
            <select
              required
              value={workerId}
              onChange={(event) => {
                setWorkerId(event.target.value)
                setSubmitError('')
              }}
            >
              <option value="">Select worker</option>
              {workers.map((worker) => (
                <option
                  key={worker.id || worker.worker_id}
                  value={worker.id || worker.worker_id}
                >
                  {worker.name || worker.id || 'NO DATA'}{worker.city ? ` · ${worker.city}` : ''}
                </option>
              ))}
            </select>
          </label>
          {workers.length === 0 && (
            <p className="muted" role="status">
              No approved workers found {selectedAlert?.city ? `in ${selectedAlert.city}` : ''}.
            </p>
          )}
          {submitError && (
            <p className="login-error" role="alert">
              {submitError}
            </p>
          )}
          <button
            className="primary"
            type="submit"
            disabled={
              submitting || eligibleAlerts.length === 0 || workers.length === 0
            }
          >
            {submitting ? 'Creating task...' : 'Create task'}
          </button>
        </form>
      </Drawer>
      <Drawer
        open={Boolean(selectedTask)}
        title={
          selectedTask?.status === 'AWAITING_REVIEW'
            ? canReviewTasks
              ? 'Official task review'
              : 'Review pending'
            : 'Task and worker details'
        }
        onClose={() => {
          setSelectedTask(null)
          setReviewNotes('')
          setReviewError('')
        }}
      >
        {selectedTask && (
          <div className="task-review-drawer">
            <dl className="detail-list">
              <dt>Task</dt>
              <dd className="mono">{selectedTask.id}</dd>
              <dt>Work item</dt>
              <dd>{selectedTask.defect || selectedTask.type || 'NO DATA'}</dd>
              <dt>Track</dt>
              <dd>{selectedTask.track || 'NO DATA'}</dd>
              <dt>Chainage</dt>
              <dd className="mono">{selectedTask.chainage || 'NO DATA'}</dd>
              <dt>Status</dt>
              <dd>
                {selectedTask.status === 'AWAITING_REVIEW'
                  ? 'Awaiting official review'
                  : selectedTask.status}
              </dd>
            </dl>
            <section className="drawer-section">
              <h3>Assigned worker</h3>
              <dl className="detail-list">
                <dt>Name</dt>
                <dd>{selectedTask.worker?.name || 'Unassigned'}</dd>
                <dt>Worker ID</dt>
                <dd className="mono">
                  {selectedTask.worker?.worker_id ||
                    selectedTask.worker_id ||
                    'NO DATA'}
                </dd>
                <dt>Email</dt>
                <dd>{selectedTask.worker?.email || 'NO DATA'}</dd>
                <dt>City</dt>
                <dd>
                  {selectedTask.worker?.city || selectedTask.city || 'NO DATA'}
                </dd>
              </dl>
            </section>
            <section className="drawer-section">
              <h3>Repair evidence</h3>
              <ReviewEvidence items={selectedTask.evidence || []} />
            </section>
            {selectedTask.review_history?.length > 0 && (
              <section className="drawer-section">
                <h3>Review history</h3>
                <ol className="review-evidence-list">
                  {selectedTask.review_history.map((entry, index) => (
                    <li key={`${entry.timestamp}-${index}`}>
                      <time>{entry.timestamp || 'NO DATE'}</time> ·{' '}
                      {entry.actor} ·{' '}
                      {entry.action
                        .replace('maintenance_task_', '')
                        .replaceAll('_', ' ')}
                      {entry.notes ? ` — ${entry.notes}` : ''}
                    </li>
                  ))}
                </ol>
              </section>
            )}
            {selectedTask.review_notes && (
              <section className="review-notice review-rework">
                <strong>Latest review instructions</strong>
                <p>{selectedTask.review_notes}</p>
              </section>
            )}
            {selectedTask.status === 'AWAITING_REVIEW' &&
              (canReviewTasks ? (
                <>
                  <label className="review-notes-field">
                    Official review notes
                    <textarea
                      value={reviewNotes}
                      onChange={(event) => {
                        setReviewNotes(event.target.value)
                        setReviewError('')
                      }}
                      placeholder="Required when requesting more work"
                      rows="4"
                    />
                  </label>
                  {reviewError && (
                    <p className="login-error" role="alert">
                      {reviewError}
                    </p>
                  )}
                  <div className="review-actions">
                    <button
                      type="button"
                      className="primary"
                      disabled={reviewBusy}
                      onClick={() => decideTaskReview('approve')}
                    >
                      {reviewBusy ? 'Saving...' : 'Approve as finished'}
                    </button>
                    <button
                      type="button"
                      className="button-secondary"
                      disabled={reviewBusy || !reviewNotes.trim()}
                      onClick={() => decideTaskReview('request_changes')}
                    >
                      {reviewBusy ? 'Saving...' : 'Request more work'}
                    </button>
                  </div>
                </>
              ) : (
                <p className="muted" role="status">
                  This task is waiting for an administrator to review it.
                </p>
              ))}
          </div>
        )}
      </Drawer>
    </>
  )
}
