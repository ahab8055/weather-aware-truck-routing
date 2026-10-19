import { useEffect, useState } from 'react'
import { getHealth } from '../api/client'

type Status = 'checking' | 'ok' | 'unreachable'

const LABELS: Record<Status, string> = {
  checking: 'Checking backend…',
  ok: 'Backend connected',
  unreachable: 'Backend unreachable',
}

function HealthStatus() {
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal)
      .then(() => setStatus('ok'))
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          console.error(error)
          setStatus('unreachable')
        }
      })
    return () => controller.abort()
  }, [])

  return (
    <p className={`health health--${status}`} role="status">
      <span className="health__dot" aria-hidden="true" />
      {LABELS[status]}
    </p>
  )
}

export default HealthStatus
