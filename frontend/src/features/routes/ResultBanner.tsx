import type { RouteEvaluationResponse } from '../../types/routes'
import type { PlannerFailure } from './apiErrors'

const FAILURE_TITLES: Record<string, string> = {
  location_not_found: 'Location not found',
  ambiguous_location: 'Which location did you mean?',
  same_location: 'Origin and destination are the same place',
  route_not_found: 'No truck route found',
  location_not_routable: 'Location is not near a truck road',
  route_too_long: 'Route too long for the routing service',
  routing_not_configured: 'Routing is not configured on the server',
  routing_auth_failed: 'Routing service rejected the server credentials',
  routing_rate_limited: 'Routing service is busy',
  routing_quota_exceeded: 'Routing service daily limit reached',
}

function failureTitle(failure: PlannerFailure): string {
  switch (failure.kind) {
    case 'validation':
      return 'Check the trip details'
    case 'routing':
      return FAILURE_TITLES[failure.code] ?? 'Routing failed'
    case 'timeout':
      return 'The request timed out'
    case 'network':
      return 'Cannot reach the server'
    case 'server':
      return 'Server error'
  }
}

interface FailureBannerProps {
  failure: PlannerFailure
  candidateField: 'origin' | 'destination' | null
  onPickCandidate: (candidate: string) => void
}

export function FailureBanner({ failure, candidateField, onPickCandidate }: FailureBannerProps) {
  const candidates = failure.kind === 'routing' ? failure.candidates : []
  return (
    <div className="banner banner--error" role="alert">
      <p className="banner__title">Evaluation failed: {failureTitle(failure)}</p>
      <p>{failure.message}</p>
      {candidates.length > 0 && (
        <div className="candidates">
          <p className="candidates__label">
            {candidateField
              ? `Pick a match to use as the ${candidateField}:`
              : 'Possible matches:'}
          </p>
          <ul>
            {candidates.map((candidate) => (
              <li key={candidate}>
                {candidateField ? (
                  <button type="button" className="button button--small" onClick={() => onPickCandidate(candidate)}>
                    {candidate}
                  </button>
                ) : (
                  candidate
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function routeLabel(response: RouteEvaluationResponse, routeId: string): string {
  const route = response.routes.find((r) => r.id === routeId)
  return route ? `Route ${route.provider_order + 1}` : routeId
}

export function EvaluationBanners({ response }: { response: RouteEvaluationResponse }) {
  if (response.routes.length === 0) {
    return (
      <div className="banner banner--warning" role="status">
        <p className="banner__title">No routes were returned for this trip.</p>
        <p>Try different locations.</p>
      </div>
    )
  }

  const unevaluated = response.routes.filter((r) => r.evaluation_status === 'weather_unavailable')
  const recommendedId = response.recommended_route_id
  const status = response.recommendation_status

  return (
    <div className="banners">
      {status === 'recommended' && recommendedId && (
        <div className="banner banner--success" role="status">
          <p className="banner__title">Recommended: {routeLabel(response, recommendedId)}</p>
          <p>{response.recommendation_message}</p>
        </div>
      )}
      {status === 'provisional' && recommendedId && (
        <div className="banner banner--provisional" role="status">
          <p className="banner__title">
            Provisional: {routeLabel(response, recommendedId)} is the safest of the fully evaluated
            routes
          </p>
          <p>{response.recommendation_message}</p>
        </div>
      )}
      {status === 'no_safe_route' && (
        <div className="banner banner--danger" role="status">
          <p className="banner__title">No safe route available</p>
          <p>{response.recommendation_message}</p>
        </div>
      )}
      {status === 'inconclusive' && (
        <div className="banner banner--danger" role="status">
          <p className="banner__title">No safe route can be confirmed</p>
          <p>{response.recommendation_message}</p>
        </div>
      )}

      {unevaluated.length > 0 && (
        <div className="banner banner--warning" role="note">
          <p className="banner__title">Route comparison may be inconclusive</p>
          <p>
            Weather could not be evaluated along{' '}
            {unevaluated.map((r) => `Route ${r.provider_order + 1}`).join(', ')}. That route
            {unevaluated.length > 1 ? 's were' : ' was'} not ranked and could be safer or less safe
            than the routes shown.
          </p>
        </div>
      )}

      {response.weather_status !== 'complete' && response.weather_note && (
        <div className="banner banner--warning" role="note">
          <p className="banner__title">
            {response.weather_status === 'unavailable' ? 'Weather unavailable' : 'Partial weather coverage'}
          </p>
          <p>{response.weather_note}</p>
        </div>
      )}

      {response.alternatives_note && (
        <div className="banner banner--info" role="note">
          <p>{response.alternatives_note}</p>
        </div>
      )}
    </div>
  )
}
