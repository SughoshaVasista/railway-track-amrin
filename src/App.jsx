import React from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import 'leaflet/dist/leaflet.css'
import './styles/tokens.css'
import './styles/base.css'
import './styles/components.css'
import Login from './pages/Login'
import Signup from './pages/Signup'
import PasswordRecovery from './pages/PasswordRecovery'
import SimulationStandalone from './pages/SimulationStandalone'
import Shell from './components/Shell'
import ProtectedRoute from './components/ProtectedRoute'
import AppErrorBoundary from './components/AppErrorBoundary'
import { AuthProvider } from './context/AuthContext'
import { ThemeProvider } from './context/ThemeContext'
import { CityProvider } from './context/CityContext'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ThemeProvider>
          <CityProvider>
            <AppErrorBoundary>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route path="/signup" element={<Signup />} />
                <Route path="/forgot-password" element={<PasswordRecovery />} />
                <Route path="/reset-password" element={<PasswordRecovery />} />
                <Route
                  path="/simulation/simulator"
                  element={
                    <ProtectedRoute allowedRoles={['admin']}>
                      <SimulationStandalone />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/simulator"
                  element={<Navigate to="/simulation/simulator" replace />}
                />
                <Route
                  path="/simulation"
                  element={<Navigate to="/simulation/simulator" replace />}
                />
                <Route
                  element={
                    <ProtectedRoute allowedRoles={['admin', 'worker']} />
                  }
                >
                  <Route path="/*" element={<Shell />} />
                </Route>
                <Route path="*" element={<Navigate to="/login" replace />} />
              </Routes>
            </AppErrorBoundary>
          </CityProvider>
        </ThemeProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}
