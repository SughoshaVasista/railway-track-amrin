import React from 'react'

const stateMap = {
  critical: ['critical', 'S3'],
  s3: ['critical', 'S3'],
  warning: ['warning', 'S2'],
  s2: ['warning', 'S2'],
  minor: ['minor', 'S1'],
  s1: ['minor', 'S1'],
  clear: ['clear', 'CLEAR'],
  online: ['clear', 'CLEAR'],
  offline: ['offline', 'OFFLINE'],
  degraded: ['degraded', 'DEGRADED'],
  timeout: ['offline', 'TIMEOUT'],
  invalid_reading: ['degraded', 'INVALID_READING'],
  missing_data: ['offline', 'MISSING_DATA'],
}

export default function SignalLamp({ state, severity, label }) {
  const [tone, defaultLabel] = stateMap[
    String(state || severity || 'offline').toLowerCase()
  ] || ['offline', 'OFFLINE']
  return (
    <span className={`signal-lamp signal-${tone}`}>
      <i aria-hidden="true" />
      <span>{label || defaultLabel}</span>
    </span>
  )
}
