import React from 'react'
import { Minus } from 'lucide-react'

export default function EmptyState({ children = 'No data available' }) {
  return (
    <div className="state-message ui-empty-state">
      <Minus size={16} aria-hidden="true" />
      {children}
    </div>
  )
}
