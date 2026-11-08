import React, { useState } from 'react'
import { Cpu } from 'lucide-react'
import Header from '../components/Header'
import Lamp from '../components/Lamp'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/StateMessage'
import { useDevices, useSensorsLatest } from '../hooks/useData'

const knownComponents = [
  ['camera', 'Camera'],
  ['ultrasonic', 'Ultrasonic'],
  ['accelerometer', 'Accelerometer'],
  ['temperature', 'Temperature'],
  ['gps', 'GPS'],
  ['ir_sensors', 'IR sensors'],
]

const noData = (value) =>
  value === undefined || value === null || value === '' ? 'NO DATA' : value

const readings = (value) =>
  Array.isArray(value)
    ? value
    : value && typeof value === 'object'
      ? Object.entries(value).map(([name, reading]) => ({
          name,
          ...(reading && typeof reading === 'object'
            ? reading
            : { value: reading }),
        }))
      : []

const readingTime = (sensor) =>
  sensor?.recorded_at ||
  sensor?.last_received_at ||
  sensor?.updated_at ||
  sensor?.timestamp

const statusFor = (sensor) => {
  const status = String(sensor?.status || '').toUpperCase()
  if (['OK', 'PASS', 'HEALTHY', 'READY', 'ACTIVE'].includes(status))
    return 'ONLINE'
  if (['FAIL', 'FAILED'].includes(status)) return 'ERROR'
  if (status) return status
  return sensor ? 'ONLINE' : 'MISSING_DATA'
}

const scalar = (value) =>
  value && typeof value === 'object'
    ? (value.value ?? value.reading ?? value.raw)
    : value

function SensorCard({ title, sensor }) {
  const status = statusFor(sensor)
  const nested =
    sensor?.value &&
    typeof sensor.value === 'object' &&
    !Array.isArray(sensor.value)
      ? sensor.value
      : {}
  const raw = { ...nested, ...(sensor || {}) }
  const value = scalar(raw.value ?? raw.reading ?? raw.raw)
  const unit = raw.unit ? ` ${raw.unit}` : ''
  const name = title.toLowerCase()
  let fields

  if (name.includes('camera')) {
    fields = [
      ['Frame rate', raw.fps == null ? 'NO DATA' : `${raw.fps} FPS`],
      [
        'Inference',
        raw.inference_ms == null ? 'NO DATA' : `${raw.inference_ms} ms`,
      ],
      ['Detections', noData(raw.detections)],
      [
        'Resolution',
        raw.width && raw.height ? `${raw.width} × ${raw.height}` : 'NO DATA',
      ],
    ]
  } else if (name.includes('accelerometer') || name === 'accel') {
    fields = [
      ['X', noData(raw.x)],
      ['Y', noData(raw.y)],
      ['Z', noData(raw.z)],
      ['Vibration', noData(raw.vibration ?? raw.vibration_state)],
      ['Anomaly score', noData(raw.anomaly_score)],
    ]
  } else if (name === 'gps') {
    fields = [
      ['Latitude', noData(raw.latitude ?? raw.lat)],
      ['Longitude', noData(raw.longitude ?? raw.lng)],
      ['Accuracy', raw.accuracy == null ? 'NO DATA' : `${raw.accuracy} m`],
      ['Satellites', noData(raw.satellites)],
      ['Fix type', noData(raw.fix_type ?? raw.fixType)],
    ]
  } else {
    fields = [
      ['Reading', value == null ? 'NO DATA' : `${value}${unit}`],
      [
        'Interpreted',
        noData(
          raw.interpreted_value ??
            raw.interpreted_value_text ??
            raw.interpreted ??
            raw.classification,
        ),
      ],
    ]
  }

  const headline = name.includes('camera')
    ? raw.fps != null
      ? `${raw.fps} FPS`
      : raw.inference_ms != null
        ? `${raw.inference_ms} ms inference`
        : 'NO DATA'
    : name === 'gps'
      ? `${noData(raw.latitude ?? raw.lat)}, ${noData(raw.longitude ?? raw.lng)}`
      : name.includes('accelerometer') || name === 'accel'
        ? noData(raw.vibration ?? raw.vibration_state ?? value)
        : value == null
          ? 'NO DATA'
          : `${value}${unit}`

  const receivedAt = readingTime(raw)
  const timeLabel = receivedAt
    ? new Date(receivedAt).toLocaleString()
    : 'No reading received yet'

  return (
    <article className="hardware-sensor-card">
      <div className="hardware-card-head">
        <h2>{title}</h2>
        <Lamp severity={status.toLowerCase()} label={status} />
      </div>
      <strong className="hardware-value">{headline}</strong>
      <p className="hardware-age">Last received: {timeLabel}</p>
      <div className="hardware-details">
        {fields.map(([label, fieldValue]) => (
          <div key={label}>
            <span>{label}</span>
            <code>{fieldValue}</code>
          </div>
        ))}
      </div>
    </article>
  )
}

export default function Hardware() {
  const [selectedDeviceId, setSelectedDeviceId] = useState('')
  const devicesState = useDevices()
  const devices = Array.isArray(devicesState.data) ? devicesState.data : []
  const device =
    devices.find((item) => item.id === selectedDeviceId) ||
    devices.find((item) =>
      /esp32/i.test(`${item.id} ${item.platform || ''}`),
    ) ||
    devices[0]
  const sensorsState = useSensorsLatest(device?.id)
  const sensorList = readings(sensorsState.data)
  const sensorsByName = Object.fromEntries(
    sensorList.map((sensor) => [
      String(sensor.name || sensor.type || '').toLowerCase(),
      sensor,
    ]),
  )
  const displayedComponents = [
    ...knownComponents.map(([key, title]) => ({
      key,
      title,
      sensor:
        sensorsByName[key] ||
        (key === 'accelerometer' ? sensorsByName.accel : null),
    })),
    ...sensorList
      .filter((sensor) => {
        const key = String(sensor.name || sensor.type || '').toLowerCase()
        return (
          !knownComponents.some(([known]) => known === key) && key !== 'accel'
        )
      })
      .map((sensor) => ({
        key: String(sensor.name || sensor.type),
        title: String(sensor.name || sensor.type || 'Sensor'),
        sensor,
      })),
  ]

  if (devicesState.loading)
    return (
      <>
        <Header
          title="Hardware"
          text="Live readings from connected components."
        />
        <LoadingState>Loading devices...</LoadingState>
      </>
    )
  if (devicesState.error)
    return (
      <>
        <Header
          title="Hardware"
          text="Live readings from connected components."
        />
        <ErrorState />
      </>
    )

  return (
    <>
      <Header
        title="Hardware"
        text="Live readings from connected components."
      />
      {devices.length > 1 && (
        <div className="toolbar-row">
          <label>
            Device
            <select
              value={device?.id || ''}
              onChange={(event) => setSelectedDeviceId(event.target.value)}
            >
              {devices.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name || item.id} · {item.platform || 'device'}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}
      {!device ? (
        <EmptyState>No registered hardware device.</EmptyState>
      ) : (
        <>
          <div className="device">
            <Cpu size={25} />
            <b>
              {device.name || device.id} <small>{device.platform || ''}</small>
            </b>
            <Lamp
              severity={String(device.status || 'missing_data').toLowerCase()}
              label={device.status || 'MISSING_DATA'}
            />
            <span className="hardware-age">
              Last sync:{' '}
              {device.last_sync || device.updated_at
                ? new Date(
                    device.last_sync || device.updated_at,
                  ).toLocaleString()
                : 'NO DATA'}
            </span>
          </div>
          {sensorsState.loading ? (
            <LoadingState>Loading component readings...</LoadingState>
          ) : sensorsState.error ? (
            <ErrorState />
          ) : (
            <div className="hardware-grid">
              {displayedComponents.map(({ key, title, sensor }) => (
                <SensorCard key={key} title={title} sensor={sensor} />
              ))}
            </div>
          )}
        </>
      )}
    </>
  )
}
