import React, { useEffect, useRef, useState } from 'react'
import { getTaskEvidenceImage } from '../services/api'

/** Loads protected API images with the same bearer token as JSON requests. */
export default function AuthenticatedImage({
  src,
  alt = '',
  className,
  onError,
  ...props
}) {
  const [objectUrl, setObjectUrl] = useState('')
  const [failed, setFailed] = useState(false)
  const onErrorRef = useRef(onError)
  onErrorRef.current = onError

  useEffect(() => {
    let active = true
    let createdUrl = ''
    setObjectUrl('')
    setFailed(false)
    if (!src) return undefined

    getTaskEvidenceImage(src)
      .then((blob) => {
        if (!active) return
        createdUrl = URL.createObjectURL(blob)
        setObjectUrl(createdUrl)
      })
      .catch(() => {
        if (active) {
          setFailed(true)
          onErrorRef.current?.()
        }
      })

    return () => {
      active = false
      if (createdUrl) URL.revokeObjectURL(createdUrl)
    }
  }, [src])

  if (failed)
    return (
      <div className="image-loading" role="status">
        Image unavailable
      </div>
    )
  if (!objectUrl)
    return (
      <div className="image-loading" role="status">
        Loading image…
      </div>
    )
  return <img {...props} className={className} src={objectUrl} alt={alt} />
}
