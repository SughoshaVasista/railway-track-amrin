import React from 'react'

export default function Header({ title, text }) {
  return (
    <div className="page-header">
      <p className="eyebrow">Operations</p>
      <h1>{title}</h1>
      <p className="muted">{text}</p>
    </div>
  )
}
