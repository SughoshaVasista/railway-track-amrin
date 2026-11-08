export function fusionLevel(sensors = []) {
  const names = new Set(
    (Array.isArray(sensors) ? sensors : Object.keys(sensors || {})).map(
      (item) =>
        String(
          typeof item === 'string' ? item : item.name || item.type || '',
        ).toLowerCase(),
    ),
  )
  if (names.has('camera') && names.has('ultrasonic')) return 'HIGH'
  if (
    names.has('camera') &&
    (names.has('vibration') || names.has('accelerometer'))
  )
    return 'MODERATE'
  if (names.has('camera')) return 'LOW'
  return 'NO DATA'
}
