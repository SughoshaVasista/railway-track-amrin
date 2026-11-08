import React from 'react'

export default class AppErrorBoundary extends React.Component {
  state = { failed: false, error: null }

  static getDerivedStateFromError(error) {
    return { failed: true, error }
  }

  componentDidCatch(error, info) {
    if (import.meta.env.DEV) {
      console.error(
        'Application render failed:',
        error?.message || 'Unknown rendering error',
        info?.componentStack || '',
      )
    }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="auth-page">
        <section className="auth-card" role="alert">
          <h1 style={{ color: '#d62839' }}>Unable to display this page</h1>
          <p className="muted">
            The application encountered an error while rendering.
          </p>
          {this.state.error && (
            <pre style={{
              background: '#222',
              color: '#ff8792',
              padding: '12px',
              borderRadius: '6px',
              overflow: 'auto',
              maxHeight: '200px',
              fontSize: '12px',
              textAlign: 'left'
            }}>
              {this.state.error.toString()}
            </pre>
          )}
          <a className="primary" href="/login" style={{ marginTop: '16px', display: 'inline-block' }}>
            Return to sign in
          </a>
        </section>
      </main>
    )
  }
}
