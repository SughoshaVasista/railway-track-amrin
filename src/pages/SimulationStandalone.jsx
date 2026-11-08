import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiErrorMessage, getDeviceSensors, getDevices } from '../services/api'
import { useAuth } from '../context/AuthContext'

const isEsp32Device = (device) =>
  String(device.source || '').toLowerCase() === 'esp32' ||
  /esp32/i.test(
    `${device.name || ''} ${device.platform || ''} ${device.model || ''}`,
  )

const valueText = (value) => {
  if (value == null || value === '') return 'No value stored'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

const readingTime = (reading) =>
  reading.recorded_at || reading.timestamp || reading.updated_at || null

export default function SimulationStandalone() {
  const { user } = useAuth()
  const [devices, setDevices] = useState([])
  const [deviceId, setDeviceId] = useState('')
  const [readings, setReadings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const device = useMemo(
    () => devices.find((item) => item.id === deviceId),
    [devices, deviceId],
  )

  useEffect(() => {
    let active = true
    const loadDevices = async () => {
      try {
        const response = await getDevices()
        const esp32Devices = (
          Array.isArray(response) ? response : response?.items || []
        ).filter((item) => item.source !== 'demo' && isEsp32Device(item))
        if (!active) return
        setDevices(esp32Devices)
        setDeviceId((current) =>
          esp32Devices.some((item) => item.id === current)
            ? current
            : esp32Devices[0]?.id || '',
        )
      } catch (loadError) {
        if (active) {
          setError(
            apiErrorMessage(
              loadError,
              'Could not load registered ESP32 devices.',
            ),
          )
          setLoading(false)
        }
      }
    }
    loadDevices()
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    if (!deviceId) {
      setReadings([])
      if (devices.length === 0) setLoading(false)
      return undefined
    }
    setLoading(true)
    setError('')
    getDeviceSensors(deviceId)
      .then((stored) => {
        if (active)
          setReadings(Array.isArray(stored) ? stored : stored?.items || [])
      })
      .catch((loadError) => {
        if (active)
          setError(
            apiErrorMessage(loadError, 'Could not load stored ESP32 readings.'),
          )
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [deviceId, devices.length])

  const lastStoredAt = useMemo(() => {
    const times = readings
      .map((reading) => Date.parse(readingTime(reading) || ''))
      .filter(Number.isFinite)
    return times.length ? new Date(Math.max(...times)) : null
  }, [readings])

  return (
    <main className="simulator stored-simulator">
      <div className="simulation-warning">
        DATABASE SNAPSHOT · ESP32 DEVICE READINGS
      </div>
      <header className="simulator-head">
        <div>
          <p className="eyebrow">Rail inspection hardware</p>
          <h1>Stored ESP32 readings</h1>
          <p className="sim-data-note">
            Read-only snapshot of readings saved by the backend. This page does
            not simulate trains or refresh live telemetry.
          </p>
        </div>
        <Link to={user?.role === 'admin' ? '/admin' : '/worker'}>
          Back to dashboard
        </Link>
      </header>

      <section
        className="sim-panel stored-readings-panel"
        aria-labelledby="stored-readings-title"
      >
        <div className="stored-readings-heading">
          <div>
            <h2 id="stored-readings-title">Device readings</h2>
            <p className="sim-device-status">
              {device
                ? `${device.name || device.id} · ${device.status || 'STATUS UNKNOWN'}`
                : 'ESP32 device'}
              {lastStoredAt
                ? ` · latest stored ${lastStoredAt.toLocaleString()}`
                : ''}
            </p>
          </div>
          {devices.length > 1 && (
            <label className="sim-device-select">
              Device
              <select
                value={deviceId}
                onChange={(event) => setDeviceId(event.target.value)}
              >
                {devices.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name || item.id}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>

        {loading ? (
          <p role="status">Loading readings stored in the database…</p>
        ) : null}
        {error ? (
          <p className="sim-missing-data" role="alert">
            {error}
          </p>
        ) : null}
        {!loading && !error && devices.length === 0 ? (
          <p className="sim-missing-data" role="status">
            No non-demo ESP32 device is registered in the database yet.
          </p>
        ) : null}
        {!loading && !error && devices.length > 0 && readings.length === 0 ? (
          <p className="sim-missing-data" role="status">
            This ESP32 has no sensor readings saved in the database.
          </p>
        ) : null}
        {!loading && readings.length > 0 ? (
          <div className="stored-reading-grid">
            {readings.map((reading, index) => (
              <article
                className="stored-reading-card"
                key={`${reading.name || reading.sensor_type || 'reading'}-${index}`}
              >
                <div className="stored-reading-title">
                  <h3>{reading.name || reading.sensor_type || 'Sensor'}</h3>
                  <span>{reading.status || 'STATUS UNKNOWN'}</span>
                </div>
                <p className="stored-reading-value">
                  {valueText(
                    reading.interpreted_value ??
                      reading.value ??
                      reading.numeric_value ??
                      reading.text_value,
                  )}
                  {reading.unit ? ` ${reading.unit}` : ''}
                </p>
                <dl>
                  <dt>Stored at</dt>
                  <dd>
                    {readingTime(reading)
                      ? new Date(readingTime(reading)).toLocaleString()
                      : 'Timestamp unavailable'}
                  </dd>
                  {reading.latitude != null && reading.longitude != null && (
                    <>
                      <dt>Location</dt>
                      <dd>
                        {reading.latitude}, {reading.longitude}
                      </dd>
                    </>
                  )}
                </dl>
              </article>
            ))}
          </div>
        ) : null}
      </section>
    </main>
  )
}
