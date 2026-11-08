import React from 'react'

export default function Toast({ children }) {
  return (
    <div className="ui-toast" role="status">
      {children}
    </div>
  )
}
