import Icon from '../../components/Icon'
import type { EvaluatedRoute, RouteEvaluationResponse } from '../../types/routes'
import { formatDuration, formatMiles, formatRiskScore } from './format'
import { ROUTE_SAFETY_LABELS, routeSafety } from './riskDisplay'
import RiskMileageBar from './RiskMileageBar'
import { routeStyle } from './routeStyles'

interface RouteComparisonProps {
  response: RouteEvaluationResponse
  selectedRouteId: string | null
  onSelectRoute: (routeId: string) => void
}

function SummaryValues({ route }: { route: EvaluatedRoute }) {
  const summary = route.summary
  return (
    <dl className="route-card__stats">
      <div>
        <dt>Distance</dt>
        <dd>{formatMiles(route.distance_miles)}</dd>
      </div>
      <div>
        <dt>Duration</dt>
        <dd>{formatDuration(route.duration_seconds)}</dd>
      </div>
      <div>
        <dt>Severe</dt>
        <dd>{summary ? formatMiles(summary.severe_miles) : 'Unavailable'}</dd>
      </div>
      <div>
        <dt>High</dt>
        <dd>{summary ? formatMiles(summary.high_miles) : 'Unavailable'}</dd>
      </div>
      <div>
        <dt>No Travel</dt>
        <dd>{summary ? formatMiles(summary.no_travel_miles) : 'Unavailable'}</dd>
      </div>
      <div>
        <dt>Avg. risk (0–3)</dt>
        <dd>
          {summary === null
            ? 'Unavailable'
            : summary.average_risk_score === null
              ? 'N/A (No Travel)'
              : formatRiskScore(summary.average_risk_score)}
        </dd>
      </div>
    </dl>
  )
}

function RouteComparison({ response, selectedRouteId, onSelectRoute }: RouteComparisonProps) {
  const reasonsByRoute = new Map(response.not_recommended.map((entry) => [entry.route_id, entry.reasons]))

  return (
    <section className="route-comparison" aria-labelledby="route-comparison-heading">
      <h2 id="route-comparison-heading" className="flex items-center gap-2">
        <Icon name="route" className="text-brand-400" />
        Routes ({response.route_count})
      </h2>
      <ul className="route-list">
        {response.routes.map((route) => {
          const safety = routeSafety(route)
          const isPick = response.safe_route_available && route.id === response.recommended_route_id
          // Only a conclusive comparison earns "Recommended"; otherwise it is a provisional pick.
          const recommended = isPick && response.recommendation_status === 'recommended'
          const provisional = isPick && response.recommendation_status === 'provisional'
          const selected = route.id === selectedRouteId
          const reasons = reasonsByRoute.get(route.id) ?? []
          const style = routeStyle(route.provider_order)
          return (
            <li key={route.id}>
              <button
                type="button"
                className={`route-card${selected ? ' route-card--selected' : ''}${recommended ? ' route-card--recommended' : ''}`}
                aria-pressed={selected}
                onClick={() => onSelectRoute(route.id)}
              >
                <span className="route-card__header">
                  <span
                    className="route-card__swatch"
                    aria-hidden="true"
                    style={{ borderTopColor: style.color, borderTopStyle: style.cssLineStyle }}
                  />
                  <span className="route-card__title">Route {route.provider_order + 1}</span>
                  {recommended && (
                    <span className="tag tag--recommended">
                      <Icon name="check" size={12} />
                      Recommended
                    </span>
                  )}
                  {provisional && <span className="tag tag--provisional">Provisional pick</span>}
                  <span className={`tag tag--${safety}`}>{ROUTE_SAFETY_LABELS[safety]}</span>
                  {route.rank !== null && (
                    <span className="tag tag--rank">
                      Rank {route.rank} of {response.ranking.length}
                    </span>
                  )}
                </span>
                <SummaryValues route={route} />
                {route.summary && <RiskMileageBar summary={route.summary} />}
                {reasons.length > 0 && (
                  <ul className="route-card__reasons">
                    {reasons.map((reason) => (
                      <li key={reason.code}>{reason.message}</li>
                    ))}
                  </ul>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

export default RouteComparison
