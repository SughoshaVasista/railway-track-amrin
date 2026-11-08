import React from 'react'

export default function Skeleton({ lines = 3 }) {
  return (
    <div className="skeleton" aria-label="Loading">
      {Array.from({ length: lines }, (_, index) => (
        <span key={index} />
      ))}
    </div>
  )
}
