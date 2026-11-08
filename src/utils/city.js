import { cities } from '../config/cities'

const coordinates = (record = {}) => {
  const gps = record.gps || record.location || {}
  const lat = record.lat ?? record.latitude ?? gps.lat ?? gps.latitude
  const lng = record.lng ?? record.longitude ?? gps.lng ?? gps.longitude
  return Number.isFinite(Number(lat)) && Number.isFinite(Number(lng))
    ? [Number(lat), Number(lng)]
    : null
}

export function cityOf(record = {}) {
  if (record.city) {
    const value = String(record.city).trim().toLowerCase()
    const match = cities.find(
      (city) => city.id === value || city.name.toLowerCase() === value,
    )
    if (match) return match.id
  }
  const point = coordinates(record)
  if (!point) return 'Unassigned'
  let nearest = null
  let distance = Infinity
  cities.forEach((city) => {
    const dLat = (point[0] - city.lat) * 111
    const dLng =
      (point[1] - city.lng) * 111 * Math.cos((city.lat * Math.PI) / 180)
    const km = Math.sqrt(dLat * dLat + dLng * dLng)
    if (km < distance) {
      distance = km
      nearest = city.id
    }
  })
  return distance <= 60 ? nearest : 'Unassigned'
}

export const coordinatesOf = coordinates
