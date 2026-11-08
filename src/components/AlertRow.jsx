import React from 'react'
import Lamp from './Lamp'

export default function AlertRow({ alert, onClick }) {
  const confidence = Number(alert.confidence)
  const confidenceText = Number.isFinite(confidence)
    ? `${Math.round(confidence <= 1 ? confidence * 100 : confidence)}%`
    : 'NO DATA'
  const openDetails = (event) => {
    event.preventDefault()
    event.stopPropagation()
    onClick?.()
  }
  return (
    <article
      className={`alert-row ${onClick ? 'interactive' : ''}`}
      role={onClick ? 'button' : undefined}
      aria-label={
        onClick
          ? `View ${alert.defect || alert.type || 'alert'} alert ${alert.id || ''}`
          : undefined
      }
      onClick={openDetails}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') openDetails(event)
      }}
      tabIndex={onClick ? 0 : undefined}
    >
      <div>
        <Lamp severity={String(alert.severity || 'offline').toLowerCase()} />
        <code>{alert.id || 'NO DATA'}</code>
      </div>
      <b>{alert.defect || alert.type || 'NO DATA'}</b>
      <small className="data-line">
        {alert.track || 'NO DATA'} · {alert.chainage || 'NO DATA'} ·{' '}
        {confidenceText}
      </small>
      <label>{alert.status || 'NO DATA'}</label>
    </article>
  )
}
