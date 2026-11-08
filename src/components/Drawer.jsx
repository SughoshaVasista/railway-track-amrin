import React from 'react'
import { X } from 'lucide-react'

export default function Drawer({ open, title, onClose, children }) {
  if (!open) return null
  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="shared-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="drawer-head">
          <h2>{title}</h2>
          <button className="icon" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </header>
        {children}
      </aside>
    </div>
  )
}
