import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import Header from '../components/Header'
import Lamp from '../components/Lamp'
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/StateMessage'
import { useDevices } from '../hooks/useData'
import { apiErrorMessage, submitCameraFrame } from '../services/api'

const MAX_SOURCE_BYTES = 20 * 1024 * 1024
const MAX_DIMENSION = 1920

async function makeJpeg(file) {
  if (!file.type.startsWith('image/')) throw new Error('Choose an image file.')
  if (file.size > MAX_SOURCE_BYTES)
    throw new Error('Choose an image smaller than 20 MB.')
  const bitmap = await createImageBitmap(file)
  try {
    const scale = Math.min(
      1,
      MAX_DIMENSION / Math.max(bitmap.width, bitmap.height),
    )
    const width = Math.max(1, Math.round(bitmap.width * scale))
    const height = Math.max(1, Math.round(bitmap.height * scale))
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    canvas.getContext('2d').drawImage(bitmap, 0, 0, width, height)
    const blob = await new Promise((resolve, reject) =>
      canvas.toBlob(
        (value) =>
          value
            ? resolve(value)
            : reject(new Error('Image conversion failed.')),
        'image/jpeg',
        0.88,
      ),
    )
    return {
      image: new File(
        [blob],
        `${file.name.replace(/\.[^.]+$/, '') || 'train-frame'}.jpg`,
        { type: 'image/jpeg' },
      ),
      width,
      height,
    }
  } finally {
    bitmap.close()
  }
}

const confidenceText = (value) =>
  value !== null &&
  value !== undefined &&
  value !== '' &&
  Number.isFinite(Number(value))
    ? `${(Number(value) * 100).toFixed(1)}%`
    : 'NO DATA'

export default function ModelDemo() {
  const devicesState = useDevices()
  const liveDevices = useMemo(
    () =>
      (Array.isArray(devicesState.data) ? devicesState.data : []).filter(
        (device) => device.source !== 'demo',
      ),
    [devicesState.data],
  )
  const [deviceId, setDeviceId] = useState('')
  const [image, setImage] = useState(null)
  const [dimensions, setDimensions] = useState(null)
  const [previewUrl, setPreviewUrl] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!deviceId && liveDevices.length) setDeviceId(liveDevices[0].id)
  }, [deviceId, liveDevices])

  useEffect(
    () => () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl)
    },
    [previewUrl],
  )

  const chooseImage = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    setError('')
    setResult(null)
    try {
      const converted = await makeJpeg(file)
      setImage(converted.image)
      setDimensions({ width: converted.width, height: converted.height })
      setPreviewUrl(URL.createObjectURL(converted.image))
    } catch (failure) {
      setImage(null)
      setDimensions(null)
      setPreviewUrl('')
      setError(failure.message || 'Could not read that image.')
    }
  }

  const runInference = async (event) => {
    event.preventDefault()
    if (!deviceId || !image) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const response = await submitCameraFrame(deviceId, image)
      setResult(response)
    } catch (failure) {
      setError(apiErrorMessage(failure, 'Model inference failed.'))
    } finally {
      setBusy(false)
    }
  }

  const boxes = Array.isArray(result?.detections) ? result.detections : []
  const hasDetections = boxes.length > 0

  return (
    <>
      <Header
        title="ML Model Demo"
        text="Upload a train image and inspect the local YOLO inference result."
      />
      <p className="model-demo-note">
        Images are converted to JPEG before upload. A positive detection is
        recorded or deduplicated as an alert for the selected device.
      </p>

      <form className="model-demo-form" onSubmit={runInference}>
        <label>
          Hardware device
          <select
            required
            value={deviceId}
            onChange={(event) => {
              setDeviceId(event.target.value)
              setResult(null)
            }}
            disabled={!liveDevices.length || busy}
          >
            {liveDevices.map((device) => (
              <option value={device.id} key={device.id}>
                {device.name || device.id} · {device.id}
              </option>
            ))}
          </select>
        </label>
        <label>
          Train image
          <input
            type="file"
            accept="image/*"
            onChange={chooseImage}
            disabled={busy}
          />
          <small>
            Images are resized to fit the model input and compressed as JPEG.
          </small>
        </label>
        {devicesState.loading && (
          <LoadingState>Loading devices...</LoadingState>
        )}
        {!devicesState.loading &&
          !devicesState.error &&
          !liveDevices.length && (
            <EmptyState>
              Register a live hardware device before running inference.
            </EmptyState>
          )}
        {devicesState.error && (
          <ErrorState>Could not load hardware devices.</ErrorState>
        )}
        {error && (
          <p className="login-error" role="alert">
            {error}
          </p>
        )}
        <button
          className="primary"
          type="submit"
          disabled={busy || !deviceId || !image}
        >
          {busy ? 'Running model…' : 'Run inference'}
        </button>
      </form>

      {previewUrl && (
        <section className="model-demo-result" aria-live="polite">
          <div
            className="model-demo-image"
            style={
              dimensions
                ? { aspectRatio: `${dimensions.width} / ${dimensions.height}` }
                : undefined
            }
          >
            <img src={previewUrl} alt="Uploaded train frame" />
            {result &&
              dimensions &&
              boxes.map((detection, index) => {
                const [x1, y1, x2, y2] = detection.box || []
                if (![x1, y1, x2, y2].every(Number.isFinite)) return null
                return (
                  <div
                    className="model-demo-box"
                    key={`${detection.class}-${index}`}
                    style={{
                      left: `${(x1 / dimensions.width) * 100}%`,
                      top: `${(y1 / dimensions.height) * 100}%`,
                      width: `${((x2 - x1) / dimensions.width) * 100}%`,
                      height: `${((y2 - y1) / dimensions.height) * 100}%`,
                    }}
                  >
                    <span>
                      {detection.class} · {confidenceText(detection.confidence)}
                    </span>
                  </div>
                )
              })}
          </div>

          {result && (
            <div className="model-demo-summary">
              <div className="model-demo-result-head">
                <h2>Inference result</h2>
                <Lamp
                  severity={hasDetections ? 'warning' : 'clear'}
                  label={hasDetections ? 'DETECTION' : 'NO DEFECT'}
                />
              </div>
              <dl className="detail-list">
                <dt>Result</dt>
                <dd>
                  {result.inference_status ||
                    (hasDetections ? 'DETECTED' : 'NO_DEFECT')}
                </dd>
                <dt>Severity</dt>
                <dd>{result.severity || 'No alert severity'}</dd>
                <dt>Confidence</dt>
                <dd>{confidenceText(result.confidence)}</dd>
                <dt>Detections</dt>
                <dd>{result.detection_count ?? boxes.length}</dd>
                <dt>Inference time</dt>
                <dd>
                  {result.inference_ms == null
                    ? 'NO DATA'
                    : `${result.inference_ms} ms`}
                </dd>
                <dt>Alert</dt>
                <dd>{result.alert_id || 'No alert created'}</dd>
              </dl>
              {result.alert_id && (
                <Link
                  className="model-demo-alert-link"
                  to={`/alerts?q=${encodeURIComponent(result.alert_id)}`}
                >
                  Open recorded alert
                </Link>
              )}
              {hasDetections ? (
                <ul className="model-demo-detections">
                  {boxes.map((detection, index) => (
                    <li key={`${detection.class}-${index}`}>
                      <b>{detection.class}</b>
                      <span>
                        Confidence {confidenceText(detection.confidence)}
                      </span>
                      <code>
                        box: [
                        {(detection.box || [])
                          .map((number) => Number(number).toFixed(1))
                          .join(', ')}
                        ]
                      </code>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">
                  The model did not return any crack detections for this image.
                </p>
              )}
            </div>
          )}
        </section>
      )}
    </>
  )
}
