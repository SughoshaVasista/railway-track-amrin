import React from 'react'
import Header from '../components/Header'
import Panel from '../components/Panel'
import { useAuth } from '../context/AuthContext'
export default function Settings() {
  const { user, logout } = useAuth()
  return (
    <>
      <Header
        title="Settings"
        text="Account details and read-only operating thresholds."
      />
      <div className="settings-grid">
        <Panel title="Profile">
          <dl className="detail-list">
            <dt>Name</dt>
            <dd>{user?.name || 'NO DATA'}</dd>
            <dt>Role</dt>
            <dd>{user?.role || 'NO DATA'}</dd>
            <dt>Worker ID</dt>
            <dd className="mono">{user?.worker_id || 'NO DATA'}</dd>
          </dl>
          <button className="primary" onClick={logout}>
            Log out
          </button>
        </Panel>
        <Panel title="Thresholds" status="Read only">
          <dl className="detail-list">
            <dt>S3 threshold</dt>
            <dd>NO DATA</dd>
            <dt>Temperature limit</dt>
            <dd>NO DATA</dd>
            <dt>Minimum safe distance</dt>
            <dd>NO DATA</dd>
          </dl>
        </Panel>
      </div>
    </>
  )
}
