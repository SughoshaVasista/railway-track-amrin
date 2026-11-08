// DEMO ONLY: creates clearly separated city records for local city-filter demonstrations.
export function demoCityRecords(records, city) {
  if (
    import.meta.env.VITE_DEMO_CITIES !== 'true' ||
    !Array.isArray(records) ||
    city === 'all'
  )
    return records
  return records.map((record) => ({ ...record, city: record.city || city }))
}
