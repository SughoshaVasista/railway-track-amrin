import React from 'react'
import { useCity } from '../context/CityContext'

export default function CityFilter() {
  const { city, setCity, cities } = useCity()
  return (
    <label className="city-filter">
      City
      <select value={city} onChange={(event) => setCity(event.target.value)}>
        <option value="all">All cities</option>
        {cities.map((item) => (
          <option key={item.id} value={item.id}>
            {item.name}
          </option>
        ))}
      </select>
    </label>
  )
}
