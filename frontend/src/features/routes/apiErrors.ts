import { ApiError } from '../../api/client'

export type FieldErrors = Partial<Record<string, string>>

export type PlannerFailure =
  | { kind: 'validation'; message: string; fieldErrors: FieldErrors }
  | {
      kind: 'routing'
      code: string
      message: string
      query?: string
      /** Which input the error is about, when the server knows. */
      field?: 'origin' | 'destination'
      candidates: string[]
    }
  | { kind: 'timeout'; message: string }
  | { kind: 'network'; message: string }
  | { kind: 'server'; status: number; message: string }

const TIMEOUT_MESSAGE =
  'The evaluation took too long. The routing or weather service may be slow. Please try again.'
const NETWORK_MESSAGE =
  'Could not reach the route planning server. Check your connection and that the backend is running.'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function routingError(body: unknown): PlannerFailure | null {
  if (!isRecord(body) || !isRecord(body.error)) return null
  const { code, message, query, field, candidates } = body.error
  if (typeof code !== 'string' || typeof message !== 'string') return null
  if (code === 'routing_timeout') return { kind: 'timeout', message }
  return {
    kind: 'routing',
    code,
    message,
    query: typeof query === 'string' ? query : undefined,
    field: field === 'origin' || field === 'destination' ? field : undefined,
    candidates: Array.isArray(candidates)
      ? candidates.filter((c): c is string => typeof c === 'string')
      : [],
  }
}

function validationError(body: unknown): PlannerFailure | null {
  if (!isRecord(body)) return null
  const fieldErrors: FieldErrors = {}
  for (const [field, messages] of Object.entries(body)) {
    if (Array.isArray(messages) && typeof messages[0] === 'string') {
      fieldErrors[field] = messages[0]
    }
  }
  if (Object.keys(fieldErrors).length === 0) return null
  return { kind: 'validation', message: 'Please correct the highlighted fields.', fieldErrors }
}

/** Turn anything thrown by the API client into a failure the planner can display. */
export function toPlannerFailure(error: unknown): PlannerFailure {
  if (error instanceof ApiError) {
    const routing = routingError(error.body)
    if (routing) return routing
    if (error.status === 400) {
      const validation = validationError(error.body)
      if (validation) return validation
    }
    if (error.status === 504) return { kind: 'timeout', message: TIMEOUT_MESSAGE }
    return {
      kind: 'server',
      status: error.status,
      message: `The server could not complete the evaluation (HTTP ${error.status}). Please try again.`,
    }
  }
  if (error instanceof DOMException && (error.name === 'TimeoutError' || error.name === 'AbortError')) {
    return { kind: 'timeout', message: TIMEOUT_MESSAGE }
  }
  return { kind: 'network', message: NETWORK_MESSAGE }
}
