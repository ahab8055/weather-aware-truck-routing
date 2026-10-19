import type {
  EvaluatedCheckpoint,
  EvaluatedRoute,
  LoadRestriction,
  RiskLevel,
  RouteRiskSummary,
  WeatherUnavailableReason,
} from '../../types/routes'

export type CheckpointRiskState = RiskLevel | 'unavailable'
export type RouteSafety = 'safe' | 'unsafe' | 'not_evaluated'

/** Every display state, lowest to highest, then missing data. */
export const LEGEND_STATES: readonly CheckpointRiskState[] = [
  'low',
  'moderate',
  'high',
  'severe',
  'no_travel',
  'unavailable',
]

export const RISK_LABELS: Record<CheckpointRiskState, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No Travel',
  unavailable: 'Weather unavailable',
}

/** Shape cue so risk is not conveyed by colour alone. */
export const RISK_SYMBOLS: Record<CheckpointRiskState, string> = {
  low: '✓',
  moderate: '!',
  high: '▲',
  severe: '▲',
  no_travel: '✕',
  unavailable: '?',
}

/** Map colours; mirror the --risk-* CSS tokens. */
export const RISK_COLORS: Record<CheckpointRiskState, string> = {
  low: '#2f9e44',
  moderate: '#e0a800',
  high: '#e8590c',
  severe: '#c92a2a',
  no_travel: '#5c1a7a',
  unavailable: '#868e96',
}

export const LOAD_RESTRICTION_TEXT: Record<LoadRestriction, string | null> = {
  none: null,
  heavy_load_wind_severe:
    'Raised to Severe: wind is 35 mph or more and the load is over 40,000 lb.',
  heavy_load_wind_no_travel:
    'Raised to No Travel: wind is 45 mph or more and the load is over 30,000 lb.',
}

export const WEATHER_REASON_TEXT: Record<WeatherUnavailableReason, string> = {
  outside_forecast_coverage: 'Arrival time is outside the available forecast (about 16 days ahead).',
  missing_values: 'The forecast for this hour is incomplete.',
  provider_error: 'The weather service could not be reached.',
  invalid_provider_data: 'The weather service returned unusable data.',
  invalid_coordinates: 'The checkpoint location is invalid.',
}

/** A checkpoint without risk is unavailable, never Low. */
export function checkpointRiskState(checkpoint: EvaluatedCheckpoint): CheckpointRiskState {
  return checkpoint.risk ? checkpoint.risk.overall : 'unavailable'
}

export function routeSafety(route: EvaluatedRoute): RouteSafety {
  if (route.evaluation_status !== 'evaluated' || route.summary === null) return 'not_evaluated'
  return route.summary.is_safe ? 'safe' : 'unsafe'
}

export const ROUTE_SAFETY_LABELS: Record<RouteSafety, string> = {
  safe: 'Safe',
  unsafe: 'Unsafe: No Travel',
  not_evaluated: 'Not fully evaluated',
}

export interface RiskSegment {
  key: string
  label: string
  miles: number
  color: string
}

/** Miles by risk band, worst first. Low and Moderate share the remainder (not split by the API). */
export function riskSegments(summary: RouteRiskSummary): RiskSegment[] {
  const flagged = summary.no_travel_miles + summary.severe_miles + summary.high_miles
  return [
    { key: 'no_travel', label: 'No Travel', miles: summary.no_travel_miles, color: RISK_COLORS.no_travel },
    { key: 'severe', label: 'Severe', miles: summary.severe_miles, color: RISK_COLORS.severe },
    { key: 'high', label: 'High', miles: summary.high_miles, color: RISK_COLORS.high },
    {
      key: 'clear',
      label: 'Low–Moderate',
      miles: Math.max(0, summary.total_distance_miles - flagged),
      color: RISK_COLORS.low,
    },
  ]
}
