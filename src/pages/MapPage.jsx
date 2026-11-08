import React from 'react'
import Header from '../components/Header'
import Panel from '../components/Panel'
import MapView from '../components/MapView'
export default function MapPage() {
  return (
    <>
      <Header
        title="Live Map"
        text="Defects, train movement and track status."
      />
      <Panel title="Track network" status="Live view">
        <MapView />
      </Panel>
    </>
  )
}
