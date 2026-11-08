import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 30000,
})

let unauthorizedHandler
export const registerUnauthorizedHandler = (handler) => {
  unauthorizedHandler = handler
}

const unwrapApiResponse = (payload) => {
  if (
    !payload ||
    typeof payload !== 'object' ||
    Array.isArray(payload) ||
    typeof payload.success !== 'boolean'
  )
    return payload
  if (!payload.success) {
    const message =
      typeof payload.error === 'string' ? payload.error : payload.error?.message
    const error = new Error(
      message || 'The server could not complete the request.',
    )
    error.code = payload.error?.code
    throw error
  }
  return Object.prototype.hasOwnProperty.call(payload, 'data')
    ? payload.data
    : payload
}

const storedAuth = () => {
  for (const storage of [window.localStorage, window.sessionStorage]) {
    const raw = storage.getItem('amrin_auth')
    if (!raw) continue
    try {
      const auth = JSON.parse(raw)
      if (auth && typeof auth === 'object') return auth
    } catch {
      storage.removeItem('amrin_auth')
    }
  }
  return null
}

api.interceptors.request.use((config) => {
  const auth = storedAuth()
  if (auth?.token) config.headers.Authorization = `Bearer ${auth.token}`
  if (typeof FormData !== 'undefined' && config.data instanceof FormData)
    config.headers.delete?.('Content-Type')
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const requestPath = String(error.config?.url || '')
    const isPublicAuthRequest = /\/auth\/(login|register)\/?$/.test(requestPath)
    const apiError = error.response?.data?.error
    const errorCode =
      (typeof apiError === 'object' ? apiError?.code : undefined) ||
      error.response?.data?.code
    const serverMessage =
      typeof apiError === 'string'
        ? apiError
        : apiError?.message ||
          error.response?.data?.detail ||
          error.response?.data?.message ||
          (typeof error.response?.data === 'string' ? error.response.data : '')
    if (apiError?.code) error.code = apiError.code
    else if (errorCode) error.code = errorCode
    if (typeof apiError === 'string' && apiError) error.message = apiError
    else if (apiError?.message) error.message = apiError.message
    // A data endpoint can return 401 for endpoint-specific reasons (or because
    // an older API has different route permissions). Only discard the saved
    // session when the API explicitly says its token/account is invalid.
    const invalidTokenMessage =
      /(?:invalid|expired|malformed).{0,30}token|token.{0,30}(?:invalid|expired)/i.test(
        String(serverMessage),
      )
    if (
      error.response?.status === 401 &&
      !isPublicAuthRequest &&
      (['invalid_token', 'invalid_account'].includes(errorCode) ||
        invalidTokenMessage)
    ) {
      error.code = errorCode || 'invalid_token'
      unauthorizedHandler?.()
    }
    return Promise.reject(error)
  },
)

export const apiErrorMessage = (
  error,
  fallback = 'The server did not accept this request.',
) =>
  (typeof error?.response?.data?.error === 'string'
    ? error.response.data.error
    : error?.response?.data?.error?.message) ||
  error?.message ||
  fallback

export const requestPasswordReset = (email) =>
  post('/auth/forgot-password', { email })
export const resetPassword = (token, password) =>
  post('/auth/reset-password', { token, password })
export const getAccounts = (params = {}) => get('/users', params)
export const adminResetPassword = (id, password) =>
  post(`/users/${encodeURIComponent(id)}/reset-password`, { password })

const get = (path, params) => {
  const cleanParams =
    params &&
    Object.fromEntries(
      Object.entries(params).filter(
        ([, value]) => value !== undefined && value !== null && value !== '',
      ),
    )
  return api
    .get(path, { params: cleanParams })
    .then(({ data }) => unwrapApiResponse(data))
}
const post = (path, body) =>
  api.post(path, body).then(({ data }) => unwrapApiResponse(data))

const rows = (value) =>
  Array.isArray(value) ? value : (value?.items ?? value?.data ?? [])
const normalizeAlert = (item = {}) => ({
  ...item,
  id: item.id ?? item.alert_id,
  defect: item.defect ?? item.defect_type,
  severity: item.severity ?? item.priority,
  image_url: item.image_url,
  track: item.track ?? item.track_id,
  gps:
    item.gps ??
    (item.latitude != null && item.longitude != null
      ? { lat: item.latitude, lng: item.longitude }
      : null),
})
const normalizeTask = (item = {}) => ({
  ...item,
  id: item.id ?? item.task_id,
  worker_id: item.worker_id ?? item.assigned_worker_id,
  priority: item.priority ?? item.severity,
  image_url: item.image_url ?? item.completion_image,
  after_image: item.after_image ?? item.completion_image,
})
const normalizeDevice = (item = {}) => ({
  ...item,
  id: item.id ?? item.device_id,
  name: item.name ?? item.device_name,
  city: item.city ?? item.location,
  updated_at: item.updated_at ?? item.last_seen,
})
const sensorTypeName = (type) =>
  ({
    CAMERA: 'Camera',
    ULTRASONIC: 'Ultrasonic',
    ACCELEROMETER: 'Accelerometer',
    TEMPERATURE: 'Temperature',
    GPS: 'GPS',
  })[String(type || '').toUpperCase()] || String(type || 'Sensor')
const sensorAxisName = (type, axis) => {
  const key = String(axis || '')
    .trim()
    .toUpperCase()
  const common = {
    LAT: 'lat',
    LATITUDE: 'lat',
    LNG: 'lng',
    LON: 'lng',
    LONGITUDE: 'lng',
    X: 'x',
    Y: 'y',
    Z: 'z',
  }
  const specific = {
    CAMERA: {
      FPS: 'fps',
      INFER: 'inference_ms',
      INFERENCE: 'inference_ms',
      DETECT: 'detections',
      DETECTIONS: 'detections',
      WIDTH: 'width',
      HEIGHT: 'height',
    },
    GPS: { SAT: 'satellites', SATELLITES: 'satellites' },
    ACCELEROMETER: { VIBRATION: 'vibration', SCORE: 'anomaly_score' },
  }
  return (
    specific[String(type || '').toUpperCase()]?.[key] ||
    common[key] ||
    key.toLowerCase() ||
    null
  )
}
const normalizeSensorReadings = (value) => {
  const items = rows(value)
  if (!items.some((item) => item?.sensor_type)) return items
  const grouped = new Map()
  items.forEach((item) => {
    const type = String(item.sensor_type || item.type || 'SENSOR').toUpperCase()
    const name = sensorTypeName(type)
    const key = name.toLowerCase()
    let sensor = grouped.get(key)
    if (!sensor) {
      sensor = {
        name,
        type,
        status: item.status || 'ONLINE',
        value: null,
        updated_at: null,
        readings: [],
      }
      grouped.set(key, sensor)
    }
    const axis = String(item.axis || '').trim()
    const field = sensorAxisName(type, axis)
    if (axis) {
      if (
        !sensor.value ||
        typeof sensor.value !== 'object' ||
        Array.isArray(sensor.value)
      )
        sensor.value = {}
      sensor.value[field] = item.value
      sensor[field] = item.value
      sensor.axis = axis
    } else {
      sensor.value = item.value
    }
    sensor.readings.push(item)
    const timestamp = item.timestamp || item.recorded_at || item.updated_at
    if (
      timestamp &&
      (!sensor.updated_at || new Date(timestamp) > new Date(sensor.updated_at))
    )
      sensor.updated_at = timestamp
    if (item.status) sensor.status = item.status
  })
  return [...grouped.values()].map((sensor) => {
    if (
      !sensor.readings.some((reading) => reading.status) &&
      sensor.updated_at
    ) {
      const age = Date.now() - new Date(sensor.updated_at).getTime()
      sensor.status =
        Number.isFinite(age) && age <= 30_000 ? 'ONLINE' : 'OFFLINE'
    }
    const collapseSingleAxis =
      sensor.value &&
      Object.keys(sensor.value).length === 1 &&
      sensor.axis &&
      ![
        'LAT',
        'LATITUDE',
        'LNG',
        'LON',
        'LONGITUDE',
        'X',
        'Y',
        'Z',
        'FPS',
        'INFER',
        'INFERENCE',
        'DETECT',
        'DETECTIONS',
        'WIDTH',
        'HEIGHT',
      ].includes(sensor.axis.toUpperCase())
    return {
      ...sensor,
      value: collapseSingleAxis ? Object.values(sensor.value)[0] : sensor.value,
    }
  })
}

export const loginRequest = (credentials) => post('/auth/login', credentials)
export const registerRequest = (body) => post('/auth/register', body)
export const getCurrentUser = () => get('/auth/me')
export const getAlerts = (filters = {}) =>
  get('/alerts', filters).then((value) => rows(value).map(normalizeAlert))
export const getAlert = (id) => get(`/alerts/${id}`).then(normalizeAlert)
export const acknowledgeAlert = (id, body) =>
  post(`/alerts/${encodeURIComponent(id)}/acknowledge`, body)
export const resolveAlert = (id, body) =>
  post(`/alerts/${encodeURIComponent(id)}/resolve`, body)
export const markFalsePositive = (id, body) =>
  post(`/alerts/${encodeURIComponent(id)}/false-positive`, body)
export const assignAlert = (id, body) =>
  post(`/alerts/${encodeURIComponent(id)}/assign`, body)
export const changeAlertPriority = (id, body) =>
  post(`/alerts/${encodeURIComponent(id)}/priority`, body)
export const getAlertHistory = (id) =>
  id
    ? get(`/alerts/${encodeURIComponent(id)}/history`).then((value) =>
        rows(value),
      )
    : Promise.resolve([])
export const getDevices = () =>
  get('/devices').then((value) => rows(value).map(normalizeDevice))
export const submitCameraFrame = (
  deviceId,
  image,
  capturedAt = new Date().toISOString(),
) => {
  const form = new FormData()
  form.append('device_id', deviceId)
  form.append('image', image, image.name || 'train-frame.jpg')
  form.append('captured_at', capturedAt)
  return api
    .post('/integrations/ml/camera/frame', form)
    .then(({ data }) => unwrapApiResponse(data))
}
export const getDeviceSensors = (id, params = {}) => {
  if (!id) return Promise.resolve([])
  const deviceId = encodeURIComponent(id)
  return get(`/devices/${deviceId}/sensors`, params).then(
    normalizeSensorReadings,
  )
}
export const getDeviceDiagnostics = (id) => {
  if (!id) return Promise.resolve(null)
  const deviceId = encodeURIComponent(id)
  return get(`/devices/${deviceId}/diagnostics`).then((value) => ({
    ...value,
    updated_at:
      value?.last_seen ?? value?.updated_at ?? value?.device?.last_seen ?? null,
    pi_status:
      value?.pi_status ??
      value?.pi?.status ??
      value?.device?.pi_status ??
      value?.device?.status ??
      value?.status ??
      null,
    network_status:
      value?.network_status ??
      value?.network?.status ??
      value?.device?.network_status ??
      value?.device?.status ??
      value?.status ??
      null,
  }))
}
export const getTasks = (params = {}) =>
  get('/tasks', params).then((value) => rows(value).map(normalizeTask))
export const createTask = (body) => post('/tasks', body).then(normalizeTask)
export const assignTask = (id, body) =>
  post(`/tasks/${encodeURIComponent(id)}/assignment`, body).then(normalizeTask)
export const unassignTask = (id) =>
  api
    .delete(`/tasks/${encodeURIComponent(id)}/assignment`)
    .then(({ data }) => normalizeTask(unwrapApiResponse(data)))
export const getWorkers = () =>
  get('/workers').then((value) =>
    rows(value).map((item) => ({
      ...item,
      id: item.id ?? item.worker_id,
      worker_id: item.worker_id ?? item.id,
      name: item.name ?? item.worker_name,
    })),
  )
export const getPendingUsers = () => get('/users/pending')
export const approveUser = (id) =>
  post(`/users/${encodeURIComponent(id)}/approve`)
export const rejectUser = (id) =>
  post(`/users/${encodeURIComponent(id)}/reject`)
export const updateTaskStatus = (id, body) =>
  api
    .put(`/tasks/${id}/status`, body)
    .then(({ data }) => unwrapApiResponse(data))
export const submitTaskForReview = (id, body = {}) =>
  post(`/tasks/${encodeURIComponent(id)}/submit`, body)
export const reviewTask = (id, body) =>
  post(`/tasks/${encodeURIComponent(id)}/review`, body)
export const uploadTaskEvidence = (taskId, formData) =>
  api
    .post(`/tasks/${encodeURIComponent(taskId)}/evidence`, formData)
    .then(({ data }) => unwrapApiResponse(data))
export const getTaskEvidenceImage = (url) => {
  const path = url.startsWith('/api/') ? url.slice(4) : url
  const requestPath = /^https?:\/\//i.test(path)
    ? new URL(path).pathname.replace(/^\/api/, '')
    : path
  return api
    .get(requestPath, {
      responseType: 'blob',
    })
    .then(({ data }) => data)
}
export const getTracks = (params = {}) => get('/tracks', params)
export const getTrains = () => get('/trains').then((value) => rows(value))
export const getSwitchStatus = (params = {}) => get('/switch/status', params)
export const getDashboardSummary = (params = {}) =>
  get('/dashboard/summary', params)
export const getDashboardEventLog = (params = {}) =>
  get('/dashboard/event-log', params).then((value) => rows(value))
export const getModelStatus = async () => {
  const status = await get('/model/status')
  if (status?.model) return status
  return {
    model: {
      loaded: status?.loaded ?? false,
      inference_active: status?.running ?? status?.active ?? false,
      name: status?.name ?? null,
      version: status?.version ?? null,
      class_count: status?.class_count ?? null,
      input_size: status?.input_size ?? null,
      inference_ms: status?.inference_ms ?? null,
      device: status?.device ?? null,
      status: status?.status ?? 'NO DATA',
    },
  }
}
export const getAIDetection = async () => {
  const status = await get('/ai/detection')
  if (status?.detection) return status
  return {
    detection: {
      ...status,
      status: status?.last_detection ? 'DETECTION RECORDED' : 'NO ML DETECTION',
    },
  }
}
