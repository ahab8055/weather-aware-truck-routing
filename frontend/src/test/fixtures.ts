/**
 * Evaluation responses shaped exactly like backend/routes/serializers.py output
 * (serialize_route_evaluation). Values are test data, not real forecasts.
 */
import type {
  CheckpointRisk,
  CheckpointWeather,
  EvaluatedCheckpoint,
  EvaluatedRoute,
  LoadRestriction,
  RiskLevel,
  RouteEvaluationResponse,
  RouteRiskSummary,
} from '../types/routes'
import type { ForecastObservation, ForecastWindowResponse } from '../types/weather'

export const DEPARTURE = '2026-10-19T08:00:00-05:00'

export function weatherAvailable(
  wind: number,
  rain: number,
  snow: number,
  forecastTime = '2026-10-19T13:00:00+00:00',
): CheckpointWeather {
  return {
    status: 'available',
    reason: null,
    message: null,
    forecast_time: forecastTime,
    wind_speed_mph: wind,
    rain_in_per_hr: rain,
    snowfall_in_per_hr: snow,
  }
}

export function weatherUnavailable(
  reason: CheckpointWeather['reason'] = 'outside_forecast_coverage',
): CheckpointWeather {
  return {
    status: 'unavailable',
    reason,
    message: 'The ETA is outside the available forecast period.',
    forecast_time: null,
    wind_speed_mph: null,
    rain_in_per_hr: null,
    snowfall_in_per_hr: null,
  }
}

export function risk(
  overall: RiskLevel,
  parts: Partial<Omit<CheckpointRisk, 'overall'>> = {},
  loadRestriction: LoadRestriction = 'none',
): CheckpointRisk {
  return {
    wind: parts.wind ?? overall,
    rain: parts.rain ?? 'low',
    snow: parts.snow ?? 'low',
    base: parts.base ?? overall,
    overall,
    load_restriction: loadRestriction,
  }
}

export function checkpoint(
  index: number,
  distanceMiles: number,
  weather: CheckpointWeather,
  checkpointRisk: CheckpointRisk | null,
): EvaluatedCheckpoint {
  const elapsed = distanceMiles * 60
  return {
    index,
    distance_miles: distanceMiles,
    latitude: 30 + distanceMiles / 69,
    longitude: -97,
    elapsed_seconds: elapsed,
    eta: new Date(Date.parse(DEPARTURE) + elapsed * 1000).toISOString().replace('.000Z', '+00:00'),
    weather,
    risk: checkpointRisk,
  }
}

export function summary(overrides: Partial<RouteRiskSummary> = {}): RouteRiskSummary {
  return {
    severe_miles: 0,
    high_miles: 0,
    no_travel_miles: 0,
    average_risk_score: 0,
    total_distance_miles: 70,
    duration_seconds: 4200,
    has_no_travel: false,
    is_safe: true,
    ...overrides,
  }
}

export function route(
  order: number,
  overrides: Partial<EvaluatedRoute> = {},
): EvaluatedRoute {
  const calm = risk('low')
  return {
    id: `route-${order + 1}`,
    provider_order: order,
    distance_miles: 70,
    duration_seconds: 4200,
    geometry: [
      [30, -97],
      [30.5, -97 + order * 0.2],
      [31, -97],
    ],
    checkpoints: [
      checkpoint(0, 0, weatherAvailable(8, 0, 0), calm),
      checkpoint(1, 25, weatherAvailable(8, 0, 0), calm),
      checkpoint(2, 50, weatherAvailable(8, 0, 0), calm),
      checkpoint(3, 70, weatherAvailable(8, 0, 0), calm),
    ],
    evaluation_status: 'evaluated',
    rank: null,
    summary: summary(),
    ...overrides,
  }
}

export function evaluation(overrides: Partial<RouteEvaluationResponse> = {}): RouteEvaluationResponse {
  return {
    origin: { query: 'Waco, TX', label: 'Waco, TX, USA', latitude: 30, longitude: -97 },
    destination: { query: 'Temple, TX', label: 'Temple, TX, USA', latitude: 31, longitude: -97 },
    departure_time: DEPARTURE,
    checkpoint_interval_miles: 25,
    load_weight_lbs: 42000,
    requested_route_count: 3,
    route_count: 0,
    alternatives_note: null,
    weather_status: 'complete',
    weather_note: null,
    recommended_route_id: null,
    safe_route_available: false,
    recommendation_message: '',
    recommendation_status: 'no_safe_route',
    comparison_conclusive: true,
    ranking: [],
    not_recommended: [],
    routes: [],
    ...overrides,
  }
}

/** Two safe routes; Route 2 has fewer Severe miles and is recommended. */
export function safeEvaluation(): RouteEvaluationResponse {
  const severe = risk('severe', { wind: 'severe' })
  const routes = [
    route(0, {
      rank: 2,
      summary: summary({ severe_miles: 12.5, average_risk_score: 0.536 }),
      checkpoints: [
        checkpoint(0, 0, weatherAvailable(8, 0, 0), risk('low')),
        checkpoint(1, 25, weatherAvailable(47, 0, 0, '2026-10-19T13:00:00+00:00'), severe),
        checkpoint(2, 50, weatherAvailable(8, 0.12, 0, '2026-10-19T14:00:00+00:00'), risk('moderate', { wind: 'low', rain: 'moderate', base: 'moderate' })),
        checkpoint(3, 70, weatherAvailable(8, 0, 0, '2026-10-19T14:00:00+00:00'), risk('low')),
      ],
    }),
    route(1, { rank: 1, duration_seconds: 4800, summary: summary({ duration_seconds: 4800 }) }),
  ]
  return evaluation({
    route_count: 2,
    routes,
    recommended_route_id: 'route-2',
    safe_route_available: true,
    recommendation_message: 'Recommended route: route-2.',
    recommendation_status: 'recommended',
    ranking: ['route-2', 'route-1'],
  })
}

/** Every route crosses No Travel conditions. */
export function allUnsafeEvaluation(): RouteEvaluationResponse {
  const noTravel = risk('no_travel', { wind: 'severe', base: 'severe' }, 'heavy_load_wind_no_travel')
  const unsafeSummary = summary({ no_travel_miles: 25, average_risk_score: null, has_no_travel: true, is_safe: false })
  const unsafeRoute = (order: number) =>
    route(order, {
      summary: unsafeSummary,
      checkpoints: [
        checkpoint(0, 0, weatherAvailable(8, 0, 0), risk('low')),
        checkpoint(1, 25, weatherAvailable(48, 0, 0), noTravel),
        checkpoint(2, 70, weatherAvailable(8, 0, 0), risk('low')),
      ],
    })
  return evaluation({
    route_count: 2,
    routes: [unsafeRoute(0), unsafeRoute(1)],
    recommendation_message: 'No safe route available: every candidate route contains No Travel conditions.',
    not_recommended: [
      { route_id: 'route-1', reasons: [{ code: 'no_travel', message: 'Contains 25.0 miles of No Travel conditions.' }] },
      { route_id: 'route-2', reasons: [{ code: 'no_travel', message: 'Contains 25.0 miles of No Travel conditions.' }] },
    ],
  })
}

/** Route 1 fully evaluated and recommended; Route 2 lacks weather at its last checkpoints. */
export function partialEvaluation(): RouteEvaluationResponse {
  const routes = [
    route(0, { rank: 1 }),
    route(1, {
      evaluation_status: 'weather_unavailable',
      summary: null,
      checkpoints: [
        checkpoint(0, 0, weatherAvailable(8, 0, 0), risk('low')),
        checkpoint(1, 25, weatherAvailable(8, 0, 0), risk('low')),
        checkpoint(2, 50, weatherUnavailable(), null),
        checkpoint(3, 70, weatherUnavailable(), null),
      ],
    }),
  ]
  return evaluation({
    route_count: 2,
    routes,
    recommended_route_id: 'route-1',
    safe_route_available: true,
    recommendation_message:
      'Provisional: route-1 is the safest of the fully evaluated routes. 1 of 2 route(s) could not be fully evaluated because weather forecasts were unavailable, so the overall comparison is inconclusive.',
    recommendation_status: 'provisional',
    comparison_conclusive: false,
    ranking: ['route-1'],
    weather_status: 'partial',
    weather_note:
      'Forecast unavailable for 2 of 8 route checkpoints: 2 outside forecast coverage (Open-Meteo serves up to 16 days ahead).',
    not_recommended: [
      {
        route_id: 'route-2',
        reasons: [
          {
            code: 'weather_unavailable',
            message:
              'Forecast unavailable for 2 of 4 checkpoints (2 outside forecast coverage (Open-Meteo serves up to 16 days ahead)); the route cannot be confirmed safe.',
          },
        ],
      },
    ],
  })
}

/** Observation in the forecast-window shape (same weather/risk objects as evaluation). */
export function observation(
  overall: RiskLevel | null,
  values: { wind?: number; rain?: number; snow?: number; forecastTime?: string } = {},
): ForecastObservation {
  if (overall === null) {
    return { weather: weatherUnavailable('missing_values'), risk: null }
  }
  return {
    weather: weatherAvailable(values.wind ?? 8, values.rain ?? 0, values.snow ?? 0, values.forecastTime),
    risk: risk(overall),
  }
}

/**
 * 0–48 h forecast window shaped like backend weather/serializers.py output.
 * `observe(locationIndex, offsetHours)` supplies each observation.
 */
export function forecastWindow(
  locations: { latitude: number; longitude: number }[],
  observe: (locationIndex: number, offsetHours: number) => ForecastObservation,
  coverageNote: string | null = null,
): ForecastWindowResponse {
  const departureMs = Date.parse(DEPARTURE)
  const utc = (offset: number) =>
    new Date(departureMs + offset * 3_600_000).toISOString().replace('.000Z', '+00:00')
  const offsets = Array.from({ length: 49 }, (_, h) => h)
  return {
    departure_time: DEPARTURE,
    load_weight_lbs: 42000,
    step_hours: 1,
    max_offset_hours: 48,
    slots: offsets.map((h) => ({ offset_hours: h, target_time: utc(h), forecast_time: utc(h) })),
    locations: locations.map((location, i) => ({
      ...location,
      observations: offsets.map((h) => {
        const obs = observe(i, h)
        return obs.weather.status === 'available'
          ? { ...obs, weather: { ...obs.weather, forecast_time: utc(h) } }
          : obs
      }),
    })),
    coverage_note: coverageNote,
  }
}
