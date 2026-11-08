import { useCallback, useEffect, useState } from 'react'

import {
  getAIDetection,
  getAlerts,
  getDashboardEventLog,
  getDashboardSummary,
  getDevices,
  getDeviceDiagnostics,
  getDeviceSensors,
  getModelStatus,
  getPendingUsers,
  getSwitchStatus,
  getTasks,
  getTracks,
  getTrains,
  getWorkers,
} from '../services/api'

import { useCity } from '../context/CityContext'
import { cityOf } from '../utils/city'

const unwrap = (value) => value?.items ?? value?.data ?? value ?? []

const cityMatches = (item, city) =>
  city === 'all' ||
  cityOf(item) === city ||
  item?.demo === true ||
  item?.source === 'demo'

function useLiveResource({ path, fetcher, deps = [], transform = unwrap }) {
  const [refreshToken, setRefreshToken] = useState(0)

  const [state, setState] = useState({
    data: null,
    loading: true,
    error: null,
    updatedAt: null,
  })

  useEffect(() => {
    let cancelled = false
    let timer
    let controller
    let delay = 3000

    const success = (value) =>
      !cancelled &&
      setState({
        data: transform(value),
        loading: false,
        error: null,
        updatedAt: Date.now(),
      })

    setState((current) => ({ ...current, loading: !current.data, error: null }))
    const poll = async () => {
      controller = new AbortController()
      try {
        const value = await fetcher(controller.signal)
        if (cancelled) return
        success(value)
        delay = 3000
      } catch (error) {
        if (!cancelled && error.name !== 'CanceledError' && error.name !== 'AbortError')
          setState((current) => ({ ...current, loading: false, error }))
        delay = Math.min(delay * 2, 60000)
      }
      if (!cancelled) timer = window.setTimeout(poll, delay)
    }
    poll()

    return () => {
      cancelled = true
      window.clearTimeout(timer)
      controller?.abort()
    }
  }, [...deps, refreshToken])

  return {
    ...state,
    refresh: () => setRefreshToken((value) => value + 1),
  }
}

export const useAlerts = (filters = {}) => {
  const { city } = useCity()

  const apiFilters = Object.fromEntries(
    Object.entries(filters).filter(([key]) =>
      ['severity', 'status', 'track', 'from', 'to'].includes(key),
    ),
  )

  return useLiveResource({
    path: 'alerts',
    fetcher: () => getAlerts(apiFilters),
    deps: [JSON.stringify(filters), city],
    transform: (value) =>
      unwrap(value)
        .filter((item) => cityMatches(item, city))
        .filter((item) =>
          Object.entries(filters).every(([key, expected]) => {
            if (!expected || ['time', 'q', 'tab'].includes(key)) {
              return true
            }

            if (key === 'type') {
              return (item.type || item.defect || item.class) === expected
            }

            return item[key] === expected
          }),
        ),
  })
}

export const useDashboardSummary = () => {
  const { city } = useCity()

  return useLiveResource({
    path: 'dashboard/summary',
    fetcher: () => getDashboardSummary({ city }),
    deps: [city],
    transform: (value) => value,
  })
}

export const useSwitchStatus = () =>
  useLiveResource({
    path: 'switch/status',
    fetcher: getSwitchStatus,
    deps: [],
  })

export const useSensorsLatest = (deviceId) =>
  useLiveResource({
    path: deviceId ? `devices/${deviceId}/sensors` : null,
    fetcher: () => getDeviceSensors(deviceId),
    deps: [deviceId],
  })

export const useSensorHistory = (deviceId, windowName = '24h') =>
  useLiveResource({
    path: null,
    fetcher: () =>
      getDeviceSensors(deviceId, {
        history: true,
        window: windowName,
      }),
    deps: [deviceId, windowName],
  })

export const useDeviceDiagnostics = (deviceId) =>
  useLiveResource({
    path: deviceId ? `devices/${deviceId}/diagnostics` : null,
    fetcher: () => getDeviceDiagnostics(deviceId),
    deps: [deviceId],
    transform: (value) => value,
  })

export const useModelStatus = () =>
  useLiveResource({
    path: null,
    fetcher: getModelStatus,
    deps: [],
    transform: (value) => value?.model ?? value,
  })

export const useAIDetection = () =>
  useLiveResource({
    path: null,
    fetcher: getAIDetection,
    deps: [],
    transform: (value) => value?.detection ?? value,
  })

export const useWorkers = () => {
  const { city } = useCity()

  return useLiveResource({
    path: null,
    fetcher: getWorkers,
    deps: [city],
    transform: (value) =>
      unwrap(value).filter((item) => cityMatches(item, city)),
  })
}

export const usePendingUsers = () =>
  useLiveResource({
    path: 'users/pending',
    fetcher: getPendingUsers,
    deps: [],
  })

export const useDevices = () => {
  const { city } = useCity()

  return useLiveResource({
    path: 'devices',
    fetcher: getDevices,
    deps: [city],
    transform: (value) =>
      unwrap(value).filter(
        (item) => cityMatches(item, city) || cityOf(item) === 'Unassigned',
      ),
  })
}

export const useTasks = (workerId) => {
  const { city } = useCity()

  return useLiveResource({
    path: workerId ? `tasks/${workerId}` : null,

    fetcher: async () => {
      const response = await getTasks(workerId ? { worker_id: workerId } : {})

      return unwrap(response).map((task) => ({
        ...task,
        id: task.id || task.task_id,
        defect: task.defect || task.type,
        type: task.type || task.defect,
      }))
    },

    deps: [workerId, city],

    transform: (value) =>
      unwrap(value).filter((item) => cityMatches(item, city)),
  })
}

export const useMapData = () => {
  const { city } = useCity()

  return useLiveResource({
    path: null,
    fetcher: () =>
      Promise.all([getTracks(), getTrains()]).then(([tracks, trains]) => ({
        tracks: unwrap(tracks).filter((item) => cityMatches(item, city)),
        trains: unwrap(trains).filter((item) => cityMatches(item, city)),
      })),
    deps: [city],
    transform: (value) => value,
  })
}

export const useEventLog = (since = '') =>
  useLiveResource({
    path: null,
    fetcher: () => getDashboardEventLog({ since }),
    deps: [since],
    transform: (value) =>
      unwrap(value).sort(
        (a, b) =>
          new Date(b.timestamp || b.created_at || 0) -
          new Date(a.timestamp || a.created_at || 0),
      ),
  })
