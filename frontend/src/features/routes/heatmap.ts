/**
 * Checkpoint-based weather heatmap helpers (display only; no risk logic).
 *
 * Each stretch of the route is coloured by the forecast at its nearest
 * checkpoint: boundaries sit halfway between consecutive checkpoints, the same
 * allocation the backend uses for route risk miles. This is a coarse
 * representation of point forecasts, not interpolated weather.
 */
import type { EvaluatedCheckpoint, EvaluatedRoute, LatLngTuple } from '../../types/routes'
import type { ForecastObservation, ForecastWindowRequest, ForecastWindowResponse } from '../../types/weather'
import type { CheckpointRiskState } from './riskDisplay'

export const FORECAST_WINDOW_HOURS = 48
export const FORECAST_STEP_HOURS = 1
export const MAX_HEATMAP_LOCATIONS = 300

const HOUR_MS = 3_600_000
const EARTH_RADIUS_MILES = 3958.7613

export interface HeatmapLocations {
  locations: ForecastWindowRequest['locations']
  indexByKey: ReadonlyMap<string, number>
}

export interface HeatmapPoint {
  checkpoint: EvaluatedCheckpoint
  observation: ForecastObservation | null
  state: CheckpointRiskState
}

export interface HeatmapSegment {
  checkpointIndex: number
  state: CheckpointRiskState
  positions: LatLngTuple[]
}

function key(latitude: number, longitude: number): string {
  return `${latitude},${longitude}`
}

/** Every distinct checkpoint coordinate across all routes, in first-seen order. */
export function uniqueCheckpointLocations(routes: EvaluatedRoute[]): HeatmapLocations {
  const indexByKey = new Map<string, number>()
  const locations: HeatmapLocations['locations'] = []
  for (const route of routes) {
    for (const { latitude, longitude } of route.checkpoints) {
      const k = key(latitude, longitude)
      if (!indexByKey.has(k)) {
        indexByKey.set(k, locations.length)
        locations.push({ latitude, longitude })
      }
    }
  }
  return { locations, indexByKey }
}

/** Nearest forecast-window hour for `etaIso`, or null when it falls outside the 0–48 h window. */
export function etaOffsetHours(departureIso: string, etaIso: string): number | null {
  const offset = Math.round((Date.parse(etaIso) - Date.parse(departureIso)) / HOUR_MS)
  return Number.isFinite(offset) && offset >= 0 && offset <= FORECAST_WINDOW_HOURS ? offset : null
}

/** Departure + offset hours, as an absolute instant (DST-safe: adds elapsed time). */
export function selectedTime(departureIso: string, offsetHours: number): Date {
  return new Date(Date.parse(departureIso) + offsetHours * HOUR_MS)
}

/** Observation and display state for each checkpoint of `route` at slot `offsetHours`. */
export function observationsAt(
  window: ForecastWindowResponse,
  indexByKey: ReadonlyMap<string, number>,
  route: EvaluatedRoute,
  offsetHours: number,
): HeatmapPoint[] {
  const slotIndex = Math.round(offsetHours / window.step_hours)
  return route.checkpoints.map((checkpoint) => {
    const locationIndex = indexByKey.get(key(checkpoint.latitude, checkpoint.longitude))
    const observation =
      locationIndex === undefined ? null : (window.locations[locationIndex]?.observations[slotIndex] ?? null)
    return {
      checkpoint,
      observation,
      state: observation?.risk ? observation.risk.overall : 'unavailable',
    }
  })
}

function haversineMiles([lat1, lon1]: LatLngTuple, [lat2, lon2]: LatLngTuple): number {
  const toRad = Math.PI / 180
  const dLat = (lat2 - lat1) * toRad
  const dLon = (lon2 - lon1) * toRad
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * toRad) * Math.cos(lat2 * toRad) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_MILES * Math.asin(Math.min(1, Math.sqrt(h)))
}

function cumulativeMiles(points: LatLngTuple[]): number[] {
  const totals = [0]
  for (let i = 1; i < points.length; i += 1) totals.push(totals[i - 1] + haversineMiles(points[i - 1], points[i]))
  return totals
}

function pointAt(points: LatLngTuple[], cumulative: number[], target: number): LatLngTuple {
  if (target <= 0) return points[0]
  const last = cumulative.length - 1
  if (target >= cumulative[last]) return points[last]
  let i = 1
  while (cumulative[i] < target) i += 1
  const span = cumulative[i] - cumulative[i - 1]
  const t = span > 0 ? (target - cumulative[i - 1]) / span : 0
  const [lat1, lon1] = points[i - 1]
  const [lat2, lon2] = points[i]
  return [lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t]
}

/**
 * Split the route polyline into one stretch per checkpoint, at the midpoints between
 * consecutive checkpoints. Checkpoint miles are scaled onto the polyline length, as
 * the backend does when placing checkpoints.
 */
export function corridorSegments(route: EvaluatedRoute, states: CheckpointRiskState[]): HeatmapSegment[] {
  const points = route.geometry
  const checkpoints = route.checkpoints
  if (points.length < 2 || checkpoints.length === 0 || route.distance_miles <= 0) return []
  const cumulative = cumulativeMiles(points)
  const length = cumulative[cumulative.length - 1]
  const scale = length / route.distance_miles
  const boundaries = [0]
  for (let i = 1; i < checkpoints.length; i += 1) {
    boundaries.push(((checkpoints[i - 1].distance_miles + checkpoints[i].distance_miles) / 2) * scale)
  }
  boundaries.push(length)

  return checkpoints.map((checkpoint, i) => {
    const start = boundaries[i]
    const end = boundaries[i + 1]
    const interior = points.filter((_, v) => cumulative[v] > start && cumulative[v] < end)
    return {
      checkpointIndex: checkpoint.index,
      state: states[i] ?? 'unavailable',
      positions: [pointAt(points, cumulative, start), ...interior, pointAt(points, cumulative, end)],
    }
  })
}

const SEVERITY: Record<CheckpointRiskState, number> = {
  unavailable: -1,
  low: 0,
  moderate: 1,
  high: 2,
  severe: 3,
  no_travel: 4,
}

/** Highest risk among `states`; missing data only when nothing was assessed. */
export function worstState(states: CheckpointRiskState[]): CheckpointRiskState {
  return states.reduce<CheckpointRiskState>(
    (worst, state) => (SEVERITY[state] > SEVERITY[worst] ? state : worst),
    'unavailable',
  )
}

/** Worst state along `route` for every slot of the window, aligned with `window.slots`. */
export function worstStateByHour(
  window: ForecastWindowResponse,
  indexByKey: ReadonlyMap<string, number>,
  route: EvaluatedRoute,
): CheckpointRiskState[] {
  return window.slots.map((slot) =>
    worstState(observationsAt(window, indexByKey, route, slot.offset_hours).map((point) => point.state)),
  )
}
