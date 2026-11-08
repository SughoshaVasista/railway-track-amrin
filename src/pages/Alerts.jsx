import React, { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Header from '../components/Header'
import AlertRow from '../components/AlertRow'
import AlertDrawer from '../components/AlertDrawer'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/StateMessage'
import { useAlerts } from '../hooks/useData'

export default function Alerts() {
  const [params, setParams] = useSearchParams()
  const [selected, setSelected] = useState(null)
  const filters = useMemo(
    () =>
      Object.fromEntries(
        ['severity', 'type', 'status', 'track', 'time'].map((key) => [
          key,
          params.get(key) || '',
        ]),
      ),
    [params],
  )
  const state = useAlerts()
  const query = params.get('q') || ''
  const tab = params.get('tab') || 'active'
  const all = Array.isArray(state.data) ? state.data : []
  const shown = all.filter((item) => {
    const type = item.type || item.defect || item.class
    if (filters.severity && item.severity !== filters.severity) return false
    if (filters.type && type !== filters.type) return false
    if (filters.status && item.status !== filters.status) return false
    if (filters.track && item.track !== filters.track) return false
    if (filters.time) {
      const timestamp = item.timestamp || item.detected_at || item.created_at
      const hours =
        filters.time === '1h' ? 1 : filters.time === '24h' ? 24 : 168
      if (
        !timestamp ||
        Date.now() - new Date(timestamp).getTime() > hours * 60 * 60 * 1000
      )
        return false
    }
    if (
      query &&
      !`${item.id} ${item.defect || item.type || ''} ${item.chainage || ''}`
        .toLowerCase()
        .includes(query.toLowerCase())
    )
      return false
    return tab === 'resolved'
      ? item.status === 'RESOLVED'
      : item.status !== 'RESOLVED'
  })
  const setFilter = (key, value) => {
    const next = new URLSearchParams(params)
    value ? next.set(key, value) : next.delete(key)
    setParams(next)
  }
  const options = (key) =>
    [
      ...new Set(
        all
          .map((item) =>
            key === 'type' ? item.type || item.defect || item.class : item[key],
          )
          .filter(Boolean),
      ),
    ].sort()
  return (
    <>
      <Header
        title="Alerts"
        text="Review, acknowledge and assign detected defects."
      />
      <div className="ui-tabs">
        <button
          className={tab === 'active' ? 'selected' : ''}
          onClick={() => setFilter('tab', 'active')}
        >
          Active
        </button>
        <button
          className={tab === 'resolved' ? 'selected' : ''}
          onClick={() => setFilter('tab', 'resolved')}
        >
          Resolved
        </button>
      </div>
      {all.length > 0 && (
        <div className="alert-filters">
          {[
            ['severity', options('severity')],
            ['type', options('type')],
            ['status', options('status')],
            ['track', options('track')],
            ['time', ['1h', '24h', '7d']],
          ].map(([key, values]) => (
            <label key={key}>
              {key}
              <select
                value={filters[key]}
                onChange={(event) => setFilter(key, event.target.value)}
              >
                <option value="">ALL</option>
                {values.map((value) => (
                  <option value={value} key={value}>
                    {value}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>
      )}
      <div className="cards">
        {state.loading ? (
          <LoadingState>Loading alerts...</LoadingState>
        ) : state.error ? (
          <ErrorState />
        ) : shown.length ? (
          shown.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              onClick={() => setSelected(alert)}
            />
          ))
        ) : (
          <EmptyState>No alerts</EmptyState>
        )}
      </div>
      <AlertDrawer
        alert={selected}
        onClose={() => setSelected(null)}
        onChanged={state.refresh}
      />
    </>
  )
}
