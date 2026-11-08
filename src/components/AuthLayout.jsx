import React from 'react'

export default function AuthLayout({ children }) {
  return (
    <main className="login login-simple">
      <section className="login-card">
        <p className="eyebrow">AMRIN</p>
        {children}
        <small>
          Simulation and decision-support software. Not live signalling control.
        </small>
      </section>
    </main>
  )
}
