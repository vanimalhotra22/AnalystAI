const BASE = import.meta.env.VITE_API_BASE || '/api'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function unwrap(res) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(data.detail || `${res.status} ${res.statusText}`, res.status)
  return data
}

export async function getJSON(path, params) {
  const url = new URL(`${BASE}${path}`, window.location.origin)
  Object.entries(params || {}).forEach(([k, v]) => v && url.searchParams.set(k, v))
  // credentials: the session is an httpOnly cookie, not a header token.
  return unwrap(await fetch(url, { credentials: 'include' }))
}

export async function postJSON(path, body) {
  return unwrap(await fetch(`${BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }))
}

// Every event type the graph emits; EventSource needs each one registered.
// NB: 'error' is reserved by EventSource for transport failures, so a failed run
// is streamed as 'run_error' to keep the two apart.
export const EVENT_TYPES = [
  'run_started', 'status', 'understanding', 'plan', 'tool_start', 'finding',
  'hypothesis', 'causal_chain', 'root_cause', 'recommendation', 'narrative',
  'report', 'run_error', 'done',
]

export function streamInvestigation({ question, period, compareTo }, onEvent) {
  const url = new URL(`${BASE}/investigate/stream`, window.location.origin)
  url.searchParams.set('question', question)
  if (period) url.searchParams.set('period', period)
  if (compareTo) url.searchParams.set('compare_to', compareTo)

  const source = new EventSource(url, { withCredentials: true })
  let finished = false
  const close = () => { finished = true; source.close() }

  EVENT_TYPES.forEach((type) => {
    source.addEventListener(type, (e) => {
      let payload = {}
      try {
        payload = JSON.parse(e.data)
      } catch (err) {
        onEvent({ type: 'run_error', message: `Malformed event payload: ${err.message}` })
        close()
        return
      }
      onEvent({ ...payload, type })
      // The server closes the connection after 'done'; without an explicit close
      // EventSource would reconnect and start the whole investigation again.
      if (type === 'done' || type === 'run_error') close()
    })
  })

  source.onerror = () => {
    if (finished) return
    onEvent({ type: 'run_error', message: 'Connection to the investigation stream was lost.' })
    close()
  }
  return close
}
