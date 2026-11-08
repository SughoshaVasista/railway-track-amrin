import React, { createContext, useContext, useMemo, useState } from 'react'
import { cities } from '../config/cities'

const CityContext = createContext(null)

export function CityProvider({ children }) {
  const [city, setCityState] = useState(() => {
    const saved = window.localStorage.getItem('amrin_city')
    const requested = new URLSearchParams(window.location.search).get('city')
    return saved || requested || 'all'
  })
  // City selection is a local map filter. Keep the current route untouched.
  const setCity = (value) => {
    setCityState(value)
    window.localStorage.setItem('amrin_city', value)
  }
  const value = useMemo(() => ({ city, setCity, cities }), [city])
  return <CityContext.Provider value={value}>{children}</CityContext.Provider>
}

export const useCity = () =>
  useContext(CityContext) || { city: 'all', setCity: () => {}, cities }
