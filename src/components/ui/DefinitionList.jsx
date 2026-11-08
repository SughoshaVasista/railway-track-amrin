import React from 'react'

export default function DefinitionList({ items }) {
  return (
    <dl className="ui-definition-list">
      {items.map(([label, value]) => (
        <React.Fragment key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </React.Fragment>
      ))}
    </dl>
  )
}
