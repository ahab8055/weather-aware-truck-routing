import type { HealthResponse } from '../types/api'
import type {
  LocationSuggestionsResponse,
  RouteCandidatesRequest,
  RouteCandidatesResponse,
  RouteEvaluationResponse,
} from '../types/routes'
import type { ForecastWindowRequest, ForecastWindowResponse } from '../types/weather'

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api'
).replace(/\/+$/, '')

export class ApiError extends Error {
  readonly status: number
  /** Parsed JSON error body, or null when the response had none. */
  readonly body: unknown

  constructor(status: number, message: string, body: unknown = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return null
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { Accept: 'application/json', ...init?.headers },
  })
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `Request to ${path} failed with status ${response.status}`,
      await readJson(response),
    )
  }
  return (await response.json()) as T
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/health/', { signal })
}

export function getRouteCandidates(
  payload: RouteCandidatesRequest,
  signal?: AbortSignal,
): Promise<RouteCandidatesResponse> {
  return request<RouteCandidatesResponse>('/routes/candidates/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

export function evaluateRoutes(
  payload: RouteCandidatesRequest,
  signal?: AbortSignal,
): Promise<RouteEvaluationResponse> {
  return request<RouteEvaluationResponse>('/routes/evaluate/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

export function getForecastWindow(
  payload: ForecastWindowRequest,
  signal?: AbortSignal,
): Promise<ForecastWindowResponse> {
  return request<ForecastWindowResponse>('/weather/forecast-window/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
}

export function getLocationSuggestions(
  query: string,
  signal?: AbortSignal,
): Promise<LocationSuggestionsResponse> {
  return request<LocationSuggestionsResponse>(
    `/routes/locations/suggest/?q=${encodeURIComponent(query)}`,
    { signal },
  )
}
