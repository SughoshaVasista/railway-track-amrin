import React, { useState } from 'react'
import { useEventLog } from '../hooks/useData'
import { EmptyState, ErrorState, LoadingState } from './StateMessage'

export default function EventLog() {
  const [since] = useState(() => new Date(Date.now() - 86400000).toISOString())
  const state = useEventLog(since)
  const events = Array.isArray(state.data) ? state.data : []
  return (
    <section className="panel event-log-panel">
      <div className="panel-head">
        <h2>Event log</h2>
        <span>{state.loading ? 'Loading' : `${events.length} events`}</span>
      </div>
      {state.loading ? (
        <LoadingState>Loading event log...</LoadingState>
      ) : state.error ? (
        <ErrorState />
      ) : events.length ? (
        <div className="event-log">
          {events.map((event, index) => (
            <article
              className="event-log-row"
              key={event.id || `${event.timestamp}-${index}`}
            >
              <time>{event.timestamp || event.created_at || 'NO DATA'}</time>
              <span>{event.message || event.event || 'NO DATA'}</span>
              <code>{event.actor || event.source || 'NO DATA'}</code>
            </article>
          ))}
        </div>
      ) : (
        <EmptyState>No events</EmptyState>
      )}
    </section>
  )
}
