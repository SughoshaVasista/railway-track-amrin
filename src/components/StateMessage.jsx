import React from 'react'
import {
  AlertCircle,
  CheckCircle2,
  ImageOff,
  MapPinOff,
  Radio,
  RadioTower,
  WifiOff,
} from 'lucide-react'
import Skeleton from './ui/Skeleton'

const icons = {
  empty: CheckCircle2,
  error: AlertCircle,
  loading: Radio,
  offline: WifiOff,
  gps: MapPinOff,
  image: ImageOff,
  simulation: RadioTower,
}

export function StateMessage({ type = 'empty', children }) {
  const Icon = icons[type] || icons.empty
  return (
    <div className={`state-message state-${type}`} role="status">
      <Icon size={22} aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}

export const EmptyState = ({ children = 'NO DATA' }) => (
  <StateMessage>{children}</StateMessage>
)
export const LoadingState = ({ children = 'Loading data...' }) => (
  <div aria-label={children}>
    <Skeleton />
  </div>
)
export const ErrorState = ({ children = 'API unavailable' }) => (
  <StateMessage type="error">{children}</StateMessage>
)
export const DeviceOffline = () => (
  <StateMessage type="offline">Device offline</StateMessage>
)
export const GpsUnavailable = () => (
  <StateMessage type="gps">GPS unavailable</StateMessage>
)
export const ImageUnavailable = () => (
  <StateMessage type="image">Image unavailable</StateMessage>
)
export const SimulationDisconnected = () => (
  <StateMessage type="simulation">Simulation disconnected</StateMessage>
)
