export type CheckpointIntervalMiles = 10 | 25 | 50

export interface RouteCandidatesRequest {
  origin: string
  destination: string
  /** ISO 8601 with a timezone offset, e.g. 2026-10-19T08:00:00-05:00 */
  departure_time: string
  checkpoint_interval_miles: CheckpointIntervalMiles
  load_weight_lbs: number
}

export interface ResolvedLocation {
  query: string
  label: string
  latitude: number
  longitude: number
}

/** [latitude, longitude], the order Leaflet expects. */
export type LatLngTuple = [number, number]

export interface RouteCheckpoint {
  index: number
  distance_miles: number
  latitude: number
  longitude: number
  elapsed_seconds: number
  /** ISO 8601, in the departure time's offset */
  eta: string
}

export interface RouteCandidate {
  id: string
  provider_order: number
  distance_miles: number
  duration_seconds: number
  geometry: LatLngTuple[]
  checkpoints: RouteCheckpoint[]
}

export interface RouteCandidatesResponse {
  origin: ResolvedLocation
  destination: ResolvedLocation
  departure_time: string
  checkpoint_interval_miles: CheckpointIntervalMiles
  load_weight_lbs: number
  requested_route_count: number
  route_count: number
  alternatives_note: string | null
  routes: RouteCandidate[]
}

export interface RoutingErrorResponse {
  error: {
    code: string
    message: string
    /** The origin or destination text a geocoding error refers to. */
    query?: string
    candidates?: string[]
  }
}

export type RiskLevel = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel'

export type LoadRestriction = 'none' | 'heavy_load_wind_severe' | 'heavy_load_wind_no_travel'

export type WeatherUnavailableReason =
  | 'outside_forecast_coverage'
  | 'missing_values'
  | 'provider_error'
  | 'invalid_provider_data'
  | 'invalid_coordinates'

export interface CheckpointWeather {
  status: 'available' | 'unavailable'
  reason: WeatherUnavailableReason | null
  message: string | null
  /** UTC ISO 8601 hour whose forecast was used */
  forecast_time: string | null
  wind_speed_mph: number | null
  rain_in_per_hr: number | null
  snowfall_in_per_hr: number | null
}

export interface CheckpointRisk {
  wind: RiskLevel
  rain: RiskLevel
  snow: RiskLevel
  base: RiskLevel
  overall: RiskLevel
  load_restriction: LoadRestriction
}

export interface EvaluatedCheckpoint extends RouteCheckpoint {
  weather: CheckpointWeather
  /** null when weather is unavailable: the checkpoint is not assessed, not assumed safe */
  risk: CheckpointRisk | null
}

export interface RouteRiskSummary {
  severe_miles: number
  high_miles: number
  no_travel_miles: number
  /** null when the route contains No Travel conditions */
  average_risk_score: number | null
  total_distance_miles: number
  duration_seconds: number
  has_no_travel: boolean
  is_safe: boolean
}

export interface EvaluatedRoute extends Omit<RouteCandidate, 'checkpoints'> {
  checkpoints: EvaluatedCheckpoint[]
  evaluation_status: 'evaluated' | 'weather_unavailable'
  rank: number | null
  summary: RouteRiskSummary | null
}

export type RecommendationStatus = 'recommended' | 'provisional' | 'no_safe_route' | 'inconclusive'

export interface NotRecommendedRoute {
  route_id: string
  reasons: { code: 'no_travel' | 'weather_unavailable'; message: string }[]
}

export interface RouteEvaluationResponse extends Omit<RouteCandidatesResponse, 'routes'> {
  weather_status: 'complete' | 'partial' | 'unavailable'
  weather_note: string | null
  recommended_route_id: string | null
  /** A fully evaluated safe route exists; see recommendation_status for whether it is definitive. */
  safe_route_available: boolean
  /**
   * recommended: all routes evaluated, safe best exists (definitive).
   * provisional: best of the evaluated routes, but some routes lack weather (inconclusive).
   * no_safe_route: all routes evaluated, all contain No Travel.
   * inconclusive: no safe evaluated route and some routes lack weather.
   */
  recommendation_status: RecommendationStatus
  /** True only when every candidate route was fully evaluated. */
  comparison_conclusive: boolean
  recommendation_message: string
  ranking: string[]
  not_recommended: NotRecommendedRoute[]
  routes: EvaluatedRoute[]
}

export interface LocationSuggestion {
  label: string
  latitude: number
  longitude: number
}

export interface LocationSuggestionsResponse {
  query: string
  suggestions: LocationSuggestion[]
}
