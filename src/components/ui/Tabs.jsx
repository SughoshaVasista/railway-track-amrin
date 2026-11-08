import React from 'react'

export default function Tabs({ items, value, onChange }) {
  return (
    <nav className="ui-tabs" aria-label="Section tabs">
      {items.map((item) => (
        <button
          key={item.value}
          className={item.value === value ? 'selected' : ''}
          onClick={() => onChange(item.value)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )
}
