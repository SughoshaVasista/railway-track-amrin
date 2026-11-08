import React from 'react'

export default function Panel({ title, status, children, className = '' }) {
  return (
    <section className={`panel ui-panel ${className}`.trim()}>
      {(title || status) && (
        <header className="panel-head">
          <h2>{title}</h2>
          {status && <span>{status}</span>}
        </header>
      )}
      {children}
    </section>
  )
}
