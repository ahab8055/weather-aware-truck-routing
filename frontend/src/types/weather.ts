import type { CheckpointRisk, CheckpointWeather } from './routes'

export interface ForecastWindowRequest {
  locations: { latitude: number; longitude: number }[]
  /** ISO 8601 with timezone offset; slot 0 is this time. */
  departure_time: string
  load_weight_lbs: number
}

export interface ForecastSlot {
  offset_hours: number
  /** departure_time + offset_hours */
  target_time: string
  /** Forecast hour actually used (UTC); null when no location had data for this slot. */
  forecast_time: string | null
}

export interface ForecastObservation {
  weather: CheckpointWeather
  /** null when weather is unavailable for this hour */
  risk: CheckpointRisk | null
}

export interface ForecastWindowLocation {
  latitude: number
  longitude: number
  /** One per slot, aligned with `slots`. */
  observations: ForecastObservation[]
}

export interface ForecastWindowResponse {
  departure_time: string
  load_weight_lbs: number
  step_hours: number
  max_offset_hours: number
  slots: ForecastSlot[]
  /** Aligned with the request's `locations`. */
  locations: ForecastWindowLocation[]
  coverage_note: string | null
}
