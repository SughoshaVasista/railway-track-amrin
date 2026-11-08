import React from 'react'

const age = (timestamp) =>
  timestamp ? Math.max(0, Math.round((Date.now() - timestamp) / 1000)) : null

export default function StatusStrip({ summaryState, alertsState }) {
  const summary = summaryState.data || {}
  const seconds = age(summaryState.updatedAt)
  const freshness =
    summaryState.error || !summaryState.updatedAt
      ? 'OFFLINE'
      : seconds < 5
        ? 'LIVE'
        : seconds < 30
          ? 'DELAYED'
          : 'OFFLINE'
  return (
    <div className="status-strip">
      <div className="status-item">
        <span>Devices online</span>
        <b>{summary.online_devices ?? 'NO DATA'}</b>
      </div>
      <div className="status-item">
        <span>Active alerts</span>
        <b>{summary.active_alerts ?? 'NO DATA'}</b>
      </div>
      <div className="status-item">
        <span>Last sync</span>
        <b className="mono">
          {summary.last_sync ||
            (summaryState.updatedAt
              ? new Date(summaryState.updatedAt).toISOString()
              : 'NO DATA')}
        </b>
      </div>
      <div className={`freshness-chip freshness-${freshness.toLowerCase()}`}>
        {freshness}
        {seconds !== null ? ` · ${seconds}s` : ''}
      </div>
      {Number(summary.s3_alerts) > 0 && (
        <span className="s3-indicator">◆ S3</span>
      )}
      {alertsState.error && (
        <span className="status-warning">Alert feed unavailable</span>
      )}
    </div>
  )
}
