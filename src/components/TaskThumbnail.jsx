import React, { useEffect, useState } from 'react'
import { api } from '../services/api'
import AuthenticatedImage from './AuthenticatedImage'

// Sample photographs are decorative only; they are never presented as task evidence.
// Photos and license details are documented in docs/train-thumbnail-attribution.md.
const samples = [
  {
    src: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/8/8a/Train_on_tracks%28GN11127%29.jpg/330px-Train_on_tracks%28GN11127%29.jpg',
    alt: 'Historic train on tracks, CC0',
  },
  {
    src: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/3/30/Indian_Railways_Train_in_2025.jpg/330px-Indian_Railways_Train_in_2025.jpg',
    alt: 'Indian Railways train by Ash7876, CC BY 4.0',
  },
  {
    src: 'https://thumb.wikimedia.org/wikipedia/commons/thumb/5/50/Tracks-train.JPG/330px-Tracks-train.JPG',
    alt: 'Train on curved tracks by Rakesh.5suthar, CC BY-SA 3.0',
  },
]

function sampleFor(taskId) {
  const key = String(taskId || 'task')
  const hash = [...key].reduce(
    (sum, character) => sum + character.charCodeAt(0),
    0,
  )
  return samples[hash % samples.length]
}

function TrainFallback() {
  return (
    <svg
      viewBox="0 0 76 76"
      role="img"
      aria-label="Train illustration"
      className="train-fallback"
    >
      <rect width="76" height="76" rx="5" fill="#dce8e8" />
      <path
        d="M0 50h76M0 56h76M8 50l8 8m8-8 8 8m8-8 8 8m8-8 8 8m8-8 8 8"
        stroke="#59666a"
        strokeWidth="2"
      />
      <path
        d="M18 16q0-5 6-5h30q6 0 6 5v25H18z"
        fill="#f4f3ef"
        stroke="#263b4a"
        strokeWidth="2"
      />
      <path d="M20 28h38v13H20z" fill="#e89a24" />
      <path d="M24 16h10v9H24zm15 0h10v9H39z" fill="#6b9eae" />
      <circle cx="29" cy="44" r="4" fill="#263b4a" />
      <circle cx="49" cy="44" r="4" fill="#263b4a" />
      <path d="M4 63h68" stroke="#263b4a" strokeWidth="3" />
    </svg>
  )
}

export default function TaskThumbnail({ taskId, src }) {
  const [evidenceFailed, setEvidenceFailed] = useState(false)
  const [sampleFailed, setSampleFailed] = useState(false)
  const sample = sampleFor(taskId)

  useEffect(() => {
    setEvidenceFailed(false)
    setSampleFailed(false)
  }, [taskId, src])

  const isExternal = (url) => {
    if (!/^https?:\/\//i.test(url || '')) return false
    try {
      const apiOrigin = new URL(api.defaults.baseURL, window.location.origin)
        .origin
      return new URL(url).origin !== apiOrigin
    } catch {
      return true
    }
  }

  const showSample = !src || evidenceFailed
  return (
    <div
      className={`worker-thumbnail ${showSample ? 'worker-thumbnail-sample' : ''}`}
    >
      {!showSample ? (
        isExternal(src) ? (
          <img
            src={src}
            alt="Task defect evidence"
            onError={() => setEvidenceFailed(true)}
          />
        ) : (
          <AuthenticatedImage
            src={src}
            alt="Task defect evidence"
            onError={() => setEvidenceFailed(true)}
          />
        )
      ) : sampleFailed ? (
        <TrainFallback />
      ) : (
        <img
          src={sample.src}
          alt={sample.alt}
          title={`${sample.alt}. Sample photo, not task evidence.`}
          onError={() => setSampleFailed(true)}
        />
      )}
      {showSample && <span className="worker-thumbnail-label">Sample</span>}
    </div>
  )
}
