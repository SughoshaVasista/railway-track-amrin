import React, { useEffect, useMemo, useState } from 'react'
import { divIcon } from 'leaflet'
import {
  MapContainer,
  Marker,
  Polyline,
  Popup,
  TileLayer,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import { Filter, LocateFixed, Maximize2, X } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { useAlerts, useMapData, useSwitchStatus } from '../hooks/useData'
import { useCity } from '../context/CityContext'
import { cities } from '../config/cities'
import {
  EmptyState,
  ErrorState,
  GpsUnavailable,
  LoadingState,
} from './StateMessage'

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const MAP_CENTER = [
  Number(import.meta.env.VITE_MAP_LAT || 12.9716),
  Number(import.meta.env.VITE_MAP_LNG || 77.5946),
]
const MAP_ZOOM = 13
const severityTone = (severity) =>
  ({ S3: 'critical', S2: 'warning', S1: 'minor' })[
    String(severity || '').toUpperCase()
  ] || 'clear'
const severityColor = (severity) =>
  ({ S3: '#D62839', S2: '#F2A93B', S1: '#5AA9E6' })[
    String(severity || '').toUpperCase()
  ] || '#35C48C'
const unwrapPosition = (item) => {
  const gps = item?.gps || item?.location || {}
  const latitude = item?.latitude ?? item?.lat ?? gps.latitude ?? gps.lat
  const longitude = item?.longitude ?? item?.lng ?? gps.longitude ?? gps.lng
  return Number.isFinite(Number(latitude)) && Number.isFinite(Number(longitude))
    ? [Number(latitude), Number(longitude)]
    : null
}
const trackPositions = (track) => {
  const geometry = track?.geometry
  const coordinates = geometry?.coordinates || track?.coordinates
  if (!Array.isArray(coordinates)) return []
  if (geometry?.type === 'LineString')
    return coordinates
      .map(([lng, lat]) => [lat, lng])
      .filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng))
  return coordinates
    .filter((point) => Array.isArray(point) && point.length >= 2)
    .map(([lat, lng]) => [Number(lat), Number(lng)])
    .filter(([lat, lng]) => Number.isFinite(lat) && Number.isFinite(lng))
}
const iconFor = (className, label) =>
  divIcon({
    className: 'map-div-icon',
    html: `<span class="${className}">${label || ''}</span>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
    popupAnchor: [0, -15],
  })

function MapGestures({ onUserGesture }) {
  useMapEvents({ dragstart: onUserGesture, zoomstart: onUserGesture })
  return null
}

function FollowTrain({ train, following }) {
  const map = useMap()
  useEffect(() => {
    const position = unwrapPosition(train)
    if (following && position)
      map.setView(position, map.getZoom(), { animate: false })
  }, [following, map, train])
  return null
}

function FitDefects({ positions, request }) {
  const map = useMap()
  useEffect(() => {
    if (!request || !positions.length) return
    map.fitBounds(positions, { padding: [24, 24], maxZoom: 16 })
  }, [map, positions, request])
  return null
}

function CityCenter({ city }) {
  const map = useMap()
  const [params] = useSearchParams()
  useEffect(() => {
    const lat = Number(params.get('lat'))
    const lng = Number(params.get('lng'))
    const zoom = Number(params.get('zoom')) || 16
    if (Number.isFinite(lat) && Number.isFinite(lng)) {
      map.setView([lat, lng], zoom, { animate: true })
      return
    }
    const target = cities.find((item) => item.id === city)
    if (target)
      map.setView([target.lat, target.lng], target.zoom, { animate: false })
    if (city === 'all')
      map.fitBounds(
        cities.map((item) => [item.lat, item.lng]),
        { padding: [24, 24] },
      )
  }, [city, map, params])
  return null
}

function FilterPanel({ filters, options, onChange, open, onClose }) {
  return (
    <section
      className={`map-filter-panel ${open ? 'open' : ''}`}
      aria-label="Map filters"
    >
      <div className="filter-panel-head">
        <h2>Filters</h2>
        <button className="icon" onClick={onClose} aria-label="Close filters">
          <X size={18} />
        </button>
      </div>
      {[
        ['severity', 'Severity', options.severities],
        ['defect', 'Defect type', options.defects],
        ['status', 'Status', options.statuses],
        ['track', 'Track', options.tracks],
      ].map(([key, label, values]) => (
        <label key={key}>
          {label}
          <select
            value={filters[key]}
            onChange={(event) => onChange(key, event.target.value)}
          >
            <option value="">All</option>
            {values.map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      ))}
      <label>
        Time range
        <select
          value={filters.timeRange}
          onChange={(event) => onChange('timeRange', event.target.value)}
        >
          <option value="">All time</option>
          <option value="1h">Last hour</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
        </select>
      </label>
    </section>
  )
}

function DetailPanel({ selected, onClose }) {
  if (!selected) return null
  const item = selected.item || {}
  const field = (value) => {
    if (value == null || value === '') return 'NO DATA'
    if (Array.isArray(value)) return value.map(field).join(', ')
    if (typeof value === 'object') {
      const reading = value.value ?? value.reading ?? value.raw
      if (value.name) return `${value.name}: ${field(reading ?? value.status)}`
      if (reading !== undefined) return field(reading)
      return Object.entries(value)
        .map(([key, entry]) => `${key}: ${field(entry)}`)
        .join(', ')
    }
    return String(value)
  }
  return (
    <section className="map-detail-panel" aria-label="Map feature details">
      <div className="detail-head">
        <div>
          <p className="eyebrow">{selected.type}</p>
          <h2>{field(item.name || item.id || item.defect || item.track)}</h2>
        </div>
        <button className="icon" onClick={onClose} aria-label="Close details">
          <X size={18} />
        </button>
      </div>
      {selected.type === 'Track' && (
        <dl>
          <dt>Status</dt>
          <dd>{field(item.status)}</dd>
          <dt>Occupancy</dt>
          <dd>{field(item.occupancy)}</dd>
          <dt>Max speed</dt>
          <dd className="mono">{field(item.max_speed ?? item.maxSpeed)}</dd>
        </dl>
      )}
      {selected.type === 'Train' && (
        <dl>
          <dt>Speed</dt>
          <dd className="mono">{field(item.speed)}</dd>
          <dt>Destination</dt>
          <dd>{field(item.destination)}</dd>
          <dt>Next switch</dt>
          <dd>{field(item.next_switch ?? item.nextSwitch)}</dd>
          <dt>Distance</dt>
          <dd className="mono">{field(item.distance)}</dd>
          <dt>GPS accuracy</dt>
          <dd className="mono">
            {field(item.gps?.accuracy ?? item.gps_accuracy)} m
          </dd>
          <dt>Satellites</dt>
          <dd className="mono">
            {field(item.gps?.satellites ?? item.satellites)}
          </dd>
          <dt>Fix type</dt>
          <dd>{field(item.gps?.fix_type ?? item.fix_type)}</dd>
        </dl>
      )}
      {selected.type === 'Defect' && (
        <dl>
          <dt>Class</dt>
          <dd>{field(item.defect || item.class)}</dd>
          <dt>Severity</dt>
          <dd>{field(item.severity)}</dd>
          <dt>Chainage</dt>
          <dd className="mono">{field(item.chainage)}</dd>
          <dt>Confidence</dt>
          <dd className="mono">{field(item.confidence)}</dd>
          <dt>Sensors</dt>
          <dd>{field(item.sensors)}</dd>
          <dt>GPS accuracy</dt>
          <dd className="mono">
            {field(item.gps?.accuracy ?? item.gps_accuracy)} m
          </dd>
          <dt>Satellites</dt>
          <dd className="mono">
            {field(item.gps?.satellites ?? item.satellites)}
          </dd>
          <dt>Fix type</dt>
          <dd>{field(item.gps?.fix_type ?? item.fix_type)}</dd>
        </dl>
      )}
      {selected.type === 'Switch' && (
        <dl>
          <dt>State</dt>
          <dd>{field(item.state || item.status)}</dd>
          <dt>Track</dt>
          <dd>{field(item.track)}</dd>
        </dl>
      )}
    </section>
  )
}

export default function MapView() {
  const { city, setCity } = useCity()
  const [searchParams, setSearchParams] = useSearchParams()
  const [following, setFollowing] = useState(false)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [fitRequest, setFitRequest] = useState(0)
  const [selected, setSelected] = useState(null)
  const mapState = useMapData()
  const alertState = useAlerts({
    severity: searchParams.get('severity') || '',
    status: searchParams.get('status') || '',
    track: searchParams.get('track') || '',
  })
  const switchState = useSwitchStatus()
  const filters = {
    severity: searchParams.get('severity') || '',
    defect: searchParams.get('defect') || '',
    status: searchParams.get('status') || '',
    track: searchParams.get('track') || '',
    timeRange: searchParams.get('timeRange') || '',
  }
  const tracks = mapState.data?.tracks || []
  const trains = mapState.data?.trains || []
  const defects = Array.isArray(alertState.data) ? alertState.data : []
  const train = trains[0]
  const trainPosition = unwrapPosition(train)
  const visibleDefects = useMemo(
    () =>
      defects.filter((defect) => {
        if (
          filters.defect &&
          defect.defect !== filters.defect &&
          defect.class !== filters.defect
        )
          return false
        if (filters.timeRange) {
          const stamp = defect.timestamp || defect.detected_at
          if (stamp) {
            const hours =
              filters.timeRange === '1h'
                ? 1
                : filters.timeRange === '24h'
                  ? 24
                  : 168
            if (Date.now() - new Date(stamp).getTime() > hours * 3600000)
              return false
          }
        }
        return true
      }),
    [defects, filters.defect, filters.timeRange],
  )
  const positions = visibleDefects.map(unwrapPosition).filter(Boolean)
  const hasFilterData = defects.length > 0
  useEffect(() => {
    if (!hasFilterData) setFiltersOpen(false)
  }, [hasFilterData])
  const options = {
    severities: [
      ...new Set(defects.map((item) => item.severity).filter(Boolean)),
    ],
    defects: [
      ...new Set(
        defects.map((item) => item.defect || item.class).filter(Boolean),
      ),
    ],
    statuses: [...new Set(defects.map((item) => item.status).filter(Boolean))],
    tracks: [...new Set(defects.map((item) => item.track).filter(Boolean))],
  }
  const updateFilter = (key, value) => {
    if (key === 'city') {
      setCity(value || 'all')
      return
    }
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next, { replace: true })
  }
  const switchPosition = unwrapPosition(switchState.data)
  const switchIcon = switchState.data
    ? iconFor(
        `switch-marker switch-${String(switchState.data.state || switchState.data.status || 'offline').toLowerCase()}`,
        '↕',
      )
    : null
  const showNoData =
    !mapState.loading &&
    !mapState.error &&
    !tracks.length &&
    !trains.length &&
    !visibleDefects.length
  return (
    <div className="map-workspace">
      <div className="map-toolbar">
        <button
          className="map-pill"
          onClick={() => setFollowing((value) => !value)}
          disabled={!trainPosition}
        >
          <LocateFixed size={15} />
          {following ? 'Following Train' : 'Follow Train'}
        </button>
        <button
          className="map-pill"
          onClick={() => setFitRequest((value) => value + 1)}
          disabled={!positions.length}
        >
          <Maximize2 size={15} />
          Fit All Defects
        </button>
        {hasFilterData && (
          <button
            className="map-pill filter-toggle"
            aria-expanded={filtersOpen}
            onClick={() => setFiltersOpen((open) => !open)}
          >
            <Filter size={15} />
            {filtersOpen ? 'Hide filters' : 'Filters'}
          </button>
        )}
      </div>
      <div className="map-city-jumps" aria-label="Jump to city">
        {cities.map((item) => (
          <button
            key={item.id}
            className={city === item.id ? 'selected' : ''}
            onClick={() => updateFilter('city', item.id)}
          >
            {item.name}
          </button>
        ))}
        <button
          className={city === 'all' ? 'selected' : ''}
          onClick={() => updateFilter('city', '')}
        >
          All cities
        </button>
      </div>
      {hasFilterData && (
        <FilterPanel
          filters={filters}
          options={options}
          onChange={updateFilter}
          open={filtersOpen}
          onClose={() => setFiltersOpen(false)}
        />
      )}
      <div className="map">
        <MapContainer
          center={MAP_CENTER}
          zoom={MAP_ZOOM}
          dragging
          tap
          className="leaflet-map"
        >
          <TileLayer
            attribution="&copy; OpenStreetMap contributors"
            url={TILE_URL}
          />
          <CityCenter city={city} />
          <MapGestures onUserGesture={() => setFollowing(false)} />
          <FollowTrain train={train} following={following} />
          <FitDefects positions={positions} request={fitRequest} />
          {tracks.map((track) => {
            const line = trackPositions(track)
            return line.length > 1 ? (
              <Polyline
                key={track.id}
                positions={line}
                pathOptions={{
                  color: severityColor(track.severity || track.max_severity),
                  weight: 5,
                }}
                eventHandlers={{
                  click: () => setSelected({ type: 'Track', item: track }),
                }}
              />
            ) : null
          })}
          {visibleDefects.map((defect) => {
            const position = unwrapPosition(defect)
            return position ? (
              <Marker
                key={defect.id}
                position={position}
                icon={iconFor(
                  `defect-marker defect-${severityTone(defect.severity)}`,
                  '',
                )}
                eventHandlers={{
                  click: () => setSelected({ type: 'Defect', item: defect }),
                }}
              >
                <Popup>
                  <b>{defect.defect || defect.class || 'NO DATA'}</b>
                  <br />
                  {defect.severity || 'NO DATA'} ·{' '}
                  {defect.confidence ?? 'NO DATA'}
                  <br />
                  {defect.chainage || 'NO DATA'}
                </Popup>
              </Marker>
            ) : null
          })}
          {trainPosition && (
            <Marker
              position={trainPosition}
              icon={iconFor('train-marker', 'T')}
              eventHandlers={{
                click: () => setSelected({ type: 'Train', item: train }),
              }}
            >
              <Popup>{train.id || 'Train'}</Popup>
            </Marker>
          )}
          {switchPosition && (
            <Marker
              position={switchPosition}
              icon={switchIcon}
              eventHandlers={{
                click: () =>
                  setSelected({ type: 'Switch', item: switchState.data }),
              }}
            >
              <Popup>
                {switchState.data.state || switchState.data.status || 'NO DATA'}
              </Popup>
            </Marker>
          )}
        </MapContainer>
        <div className="map-legend">
          <strong>Legend</strong>
          <span>
            <i className="legend-s3">◆</i>S3
          </span>
          <span>
            <i className="legend-s2">▲</i>S2
          </span>
          <span>
            <i className="legend-s1">●</i>S1
          </span>
          <span>
            <i className="legend-train">T</i>Train
          </span>
          <span>
            <i className="legend-track" />
            Track
          </span>
        </div>
        {mapState.loading && <LoadingState>Loading map data...</LoadingState>}
        {mapState.error && <ErrorState>API unavailable</ErrorState>}
        {!mapState.loading &&
          !mapState.error &&
          trains.length > 0 &&
          !trainPosition && <GpsUnavailable />}
        {showNoData && <EmptyState>Map data unavailable</EmptyState>}
      </div>
      <DetailPanel selected={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
