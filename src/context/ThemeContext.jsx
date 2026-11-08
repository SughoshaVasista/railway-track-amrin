import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

const ThemeContext = createContext(null)

function initialTheme() {
  const saved = window.localStorage.getItem('amrin_theme')
  if (saved === 'dark' || saved === 'light') return saved
  return 'light'
}

export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem('amrin_theme', theme)
  }, [theme])
  const value = useMemo(
    () => ({
      theme,
      setTheme,
      toggleTheme: () =>
        setTheme((value) => (value === 'dark' ? 'light' : 'dark')),
    }),
    [theme],
  )
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
