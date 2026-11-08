import React from 'react'

export default function Panel({ title, status, className = '', children }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        <span>{status}</span>
      </div>
      {children}
    </section>
  )
}
