import React from 'react'
import { Circle, Diamond, Triangle } from 'lucide-react'

const glyphs = { S1: Circle, S2: Triangle, S3: Diamond }

export default function SeverityBadge({ severity }) {
  const value = String(severity || 'NO DATA').toUpperCase()
  const Glyph = glyphs[value]
  return (
    <span className={`severity-badge severity-${value.toLowerCase()}`}>
      {Glyph && <Glyph size={11} fill="currentColor" aria-hidden="true" />}{' '}
      {value}
    </span>
  )
}
