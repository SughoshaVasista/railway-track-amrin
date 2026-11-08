import React from 'react'

export default function ConfidenceChip({ value }) {
  const numeric = Number(value)
  const level = Number.isFinite(numeric)
    ? numeric >= 0.9
      ? 'HIGH'
      : numeric >= 0.7
        ? 'MODERATE'
        : 'LOW'
    : 'NO DATA'
  return (
    <span className={`confidence-chip confidence-${level.toLowerCase()}`}>
      {level}
      {Number.isFinite(numeric) ? ` ${Math.round(numeric * 100)}%` : ''}
    </span>
  )
}
