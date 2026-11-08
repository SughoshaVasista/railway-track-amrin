import React, { useState } from 'react'
import {
  AlertTriangle,
  ScanSearch,
  ChevronsLeft,
  ChevronsRight,
  Cpu,
  LayoutDashboard,
  ListTodo,
  Map,
  Settings,
  X,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

const groups = [
  {
    title: 'Operations',
    items: [
      ['/admin', 'Command Center', LayoutDashboard],
      ['/map', 'Live Map', Map],
      ['/alerts', 'Alerts', AlertTriangle],
      ['/tasks', 'Tasks', ListTodo],
    ],
  },
  {
    title: 'Maintenance',
    items: [
      ['/hardware', 'Hardware', Cpu],
      ['/model-demo', 'ML Model Demo', ScanSearch],
    ],
  },
]

const mobileItems = [
  ['/admin', 'Command Center', LayoutDashboard],
  ['/map', 'Map', Map],
  ['/alerts', 'Alerts', AlertTriangle],
  ['/tasks', 'Tasks', ListTodo],
]
const moreItems = [
  ['/model-demo', 'ML Model Demo', ScanSearch],
  ['/settings', 'Settings', Settings],
]

function LinkItem({ to, label, Icon, onClick }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
    >
      <Icon size={18} />
      <span>{label}</span>
    </NavLink>
  )
}

export default function Nav() {
  const { user } = useAuth()
  const [moreOpen, setMoreOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem('amrin_sidebar_collapsed') === 'true',
  )
  const toggle = () =>
    setCollapsed((value) => {
      window.localStorage.setItem('amrin_sidebar_collapsed', String(!value))
      return !value
    })
  if (!user) return null
  const visibleGroups =
    user.role === 'admin'
      ? groups
      : [
          {
            title: 'Operations',
            items: [
              ['/worker', 'Tasks', ListTodo],
              ['/map', 'Map', Map],
            ],
          },
        ]
  const visibleMobileItems =
    user.role === 'admin'
      ? mobileItems
      : [
          ['/worker', 'Tasks', ListTodo],
          ['/map', 'Map', Map],
        ]
  const visibleMoreItems = user.role === 'admin' ? moreItems : []
  return (
    <>
      <aside
        className={`sidebar ${collapsed ? 'sidebar-collapsed' : ''}`}
        aria-label="Primary navigation"
      >
        <button
          className="sidebar-toggle icon"
          onClick={toggle}
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? <ChevronsRight size={16} /> : <ChevronsLeft size={16} />}
        </button>
        {visibleGroups.map((group) => (
          <section className="nav-group" key={group.title}>
            <h2>{group.title}</h2>
            {group.items.map(([to, label, Icon]) => (
              <LinkItem key={to} to={to} label={label} Icon={Icon} />
            ))}
          </section>
        ))}
      </aside>
      <nav className="mobile-nav" aria-label="Mobile navigation">
        {visibleMobileItems.map(([to, label, Icon]) => (
          <LinkItem key={to} to={to} label={label} Icon={Icon} />
        ))}
        {visibleMoreItems.length > 0 && (
          <button
            className="nav-link more-button"
            onClick={() => setMoreOpen(true)}
            aria-label="Open more navigation"
          >
            <Settings size={18} />
            <span>More</span>
          </button>
        )}
      </nav>
      {moreOpen && visibleMoreItems.length > 0 && (
        <div
          className="sheet-backdrop"
          role="presentation"
          onClick={() => setMoreOpen(false)}
        >
          <section
            className="more-sheet"
            role="dialog"
            aria-modal="true"
            aria-label="More navigation"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="sheet-head">
              <h2>More</h2>
              <button
                className="icon"
                onClick={() => setMoreOpen(false)}
                aria-label="Close more navigation"
              >
                <X size={19} />
              </button>
            </div>
            {visibleMoreItems.map(([to, label, Icon]) => (
              <LinkItem
                key={to}
                to={to}
                label={label}
                Icon={Icon}
                onClick={() => setMoreOpen(false)}
              />
            ))}
          </section>
        </div>
      )}
    </>
  )
}
