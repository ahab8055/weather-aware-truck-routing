"""Weather-aware evaluation of route candidates.

Fetches forecasts for every checkpoint ETA, classifies them with the risk
engine, summarizes each route and recommends the safest one.

Missing-data policy: a route is only summarized and ranked when every one of
its checkpoints has a usable forecast. A route with any unavailable forecast
is never treated as safe; it is reported as not evaluated, with the reason.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from risk.engine import CheckpointRisk, assess_checkpoint
from risk.levels import RiskLevel
from risk.recommendation import NO_SAFE_ROUTE_MESSAGE, recommend_route
from risk.summary import RouteCheckpoint, RouteRiskSummary, summarize_route
from routes.checkpoints import Checkpoint
from routes.services import RouteCandidate, RouteCandidates
from weather.errors import WeatherError
from weather.forecast import (
    OUTSIDE_COVERAGE,
    NormalizedWeather,
    WeatherUnavailable,
    forecast_window,
    location_key,
    select_forecast,
)
from weather.open_meteo import HourlySeries
from weather.window import HourlyForecastSource

EVALUATED = "evaluated"
WEATHER_UNAVAILABLE = "weather_unavailable"

# Recommendation status: only `recommended` is a definitive safest-route answer.
RECOMMENDED = "recommended"  # every route evaluated; a safe best route exists
PROVISIONAL = "provisional"  # best of the evaluated routes, but some routes are incomplete
NO_SAFE_ROUTE = "no_safe_route"  # every route evaluated; all contain No Travel
INCONCLUSIVE = "inconclusive"  # no safe evaluated route and some routes are incomplete

WEATHER_COMPLETE = "complete"
WEATHER_PARTIAL = "partial"
WEATHER_NONE = "unavailable"

_REASON_LABELS = {
    OUTSIDE_COVERAGE: "outside forecast coverage (Open-Meteo serves up to 16 days ahead)",
    "missing_values": "missing forecast values",
    "provider_error": "weather provider error",
    "invalid_provider_data": "unusable weather provider data",
    "invalid_coordinates": "invalid coordinates",
}


@dataclass(frozen=True)
class CheckpointEvaluation:
    checkpoint: Checkpoint
    weather: NormalizedWeather | WeatherUnavailable
    risk: CheckpointRisk | None

    @property
    def has_weather(self) -> bool:
        return self.risk is not None


@dataclass(frozen=True)
class NotRecommendedReason:
    code: str
    message: str


@dataclass(frozen=True)
class RouteEvaluationResult:
    candidate: RouteCandidate
    status: str
    checkpoints: tuple[CheckpointEvaluation, ...]
    summary: RouteRiskSummary | None
    rank: int | None
    not_recommended_reasons: tuple[NotRecommendedReason, ...]


@dataclass(frozen=True)
class RouteEvaluation:
    candidates: RouteCandidates
    routes: tuple[RouteEvaluationResult, ...]
    recommended_route_id: str | None
    ranking: tuple[str, ...]
    message: str
    weather_status: str
    weather_note: str | None
    recommendation_status: str

    @property
    def safe_route_available(self) -> bool:
        """A fully evaluated, safe route exists (it may still be only a provisional pick)."""
        return self.recommended_route_id is not None

    @property
    def comparison_conclusive(self) -> bool:
        """True only when every candidate route was fully evaluated."""
        return self.recommendation_status in (RECOMMENDED, NO_SAFE_ROUTE)


def _fetch_forecasts(
    candidates: RouteCandidates, source: HourlyForecastSource, now: datetime
) -> dict[tuple[float, float], HourlySeries | WeatherError]:
    """One deduplicated, batched fetch covering every checkpoint of every route."""
    checkpoints = [c for route in candidates.routes for c in route.checkpoints]
    keys = list(dict.fromkeys(location_key(c.latitude, c.longitude) for c in checkpoints))
    window = forecast_window([c.eta for c in checkpoints], now)
    if window is None or not keys:
        return {}
    return dict(zip(keys, source.fetch_hourly(keys, *window)))


def _evaluate_checkpoint(
    checkpoint: Checkpoint,
    forecasts: dict[tuple[float, float], HourlySeries | WeatherError],
    load_weight_lbs: float,
) -> CheckpointEvaluation:
    series = forecasts.get(location_key(checkpoint.latitude, checkpoint.longitude))
    weather = select_forecast(series, checkpoint.eta)
    risk = (
        assess_checkpoint(weather.to_conditions(), load_weight_lbs)
        if isinstance(weather, NormalizedWeather)
        else None
    )
    return CheckpointEvaluation(checkpoint=checkpoint, weather=weather, risk=risk)


def _summarize(route: RouteCandidate, checkpoints: Sequence[CheckpointEvaluation]):
    if not all(c.has_weather for c in checkpoints):
        return None
    return summarize_route(
        route.id,
        [RouteCheckpoint(distance_miles=c.checkpoint.distance_miles, risk=c.risk) for c in checkpoints],
        route.distance_miles,
        route.duration_seconds,
    )


def _reason_breakdown(reasons: Counter) -> str:
    return ", ".join(f"{count} {_REASON_LABELS.get(reason, reason)}" for reason, count in reasons.items())


def _not_recommended_reasons(
    checkpoints: Sequence[CheckpointEvaluation], summary: RouteRiskSummary | None
) -> tuple[NotRecommendedReason, ...]:
    reasons = []
    no_travel_count = sum(1 for c in checkpoints if c.risk and c.risk.overall is RiskLevel.NO_TRAVEL)
    if summary is not None and summary.has_no_travel:
        reasons.append(
            NotRecommendedReason(
                "no_travel",
                f"Contains {summary.no_travel_miles:.1f} miles of No Travel conditions.",
            )
        )
    elif no_travel_count:
        reasons.append(
            NotRecommendedReason(
                "no_travel", f"No Travel conditions at {no_travel_count} checkpoint(s)."
            )
        )
    missing = Counter(c.weather.reason for c in checkpoints if not c.has_weather)
    if missing:
        reasons.append(
            NotRecommendedReason(
                WEATHER_UNAVAILABLE,
                f"Forecast unavailable for {sum(missing.values())} of {len(checkpoints)} "
                f"checkpoints ({_reason_breakdown(missing)}); the route cannot be confirmed safe.",
            )
        )
    return tuple(reasons)


def _weather_status(evaluations: Sequence[CheckpointEvaluation]) -> tuple[str, str | None]:
    missing = Counter(e.weather.reason for e in evaluations if not e.has_weather)
    if not missing:
        return WEATHER_COMPLETE, None
    status = WEATHER_NONE if sum(missing.values()) == len(evaluations) else WEATHER_PARTIAL
    note = (
        f"Forecast unavailable for {sum(missing.values())} of {len(evaluations)} route "
        f"checkpoints: {_reason_breakdown(missing)}."
    )
    return status, note


def _recommendation_status(has_recommendation: bool, unevaluated: int) -> str:
    if has_recommendation:
        return PROVISIONAL if unevaluated else RECOMMENDED
    return INCONCLUSIVE if unevaluated else NO_SAFE_ROUTE


def _message(
    recommendation_message: str | None,
    recommended_route_id: str | None,
    unevaluated: int,
    unsafe: int,
    total: int,
) -> str:
    if recommendation_message is not None:
        if unevaluated:
            return (
                f"Provisional: {recommended_route_id} is the safest of the fully evaluated routes. "
                f"{unevaluated} of {total} route(s) could not be fully evaluated because weather "
                "forecasts were unavailable, so the overall comparison is inconclusive."
            )
        return recommendation_message
    if unevaluated:
        message = (
            f"No safe route can be confirmed: weather forecasts are unavailable for "
            f"{unevaluated} of {total} route(s)"
        )
        if unsafe:
            message += f", and the other {unsafe} contain No Travel conditions"
        return message + "."
    return NO_SAFE_ROUTE_MESSAGE


def evaluate_routes(
    candidates: RouteCandidates, source: HourlyForecastSource, now: datetime | None = None
) -> RouteEvaluation:
    """Attach forecasts and risk to every checkpoint, summarize routes and recommend one."""
    now = now or datetime.now(UTC)
    forecasts = _fetch_forecasts(candidates, source, now)

    per_route = []
    for route in candidates.routes:
        checkpoints = tuple(
            _evaluate_checkpoint(c, forecasts, candidates.load_weight_lbs) for c in route.checkpoints
        )
        per_route.append((route, checkpoints, _summarize(route, checkpoints)))

    # Provider order is preserved, so recommend_route's ties fall back to it.
    summaries = [summary for _, _, summary in per_route if summary is not None]
    recommendation = recommend_route(summaries) if summaries else None
    ranks = (
        {r.summary.route_id: r.rank for r in recommendation.ranked_safe_routes}
        if recommendation
        else {}
    )

    results = tuple(
        RouteEvaluationResult(
            candidate=route,
            status=EVALUATED if summary is not None else WEATHER_UNAVAILABLE,
            checkpoints=checkpoints,
            summary=summary,
            rank=ranks.get(route.id),
            not_recommended_reasons=_not_recommended_reasons(checkpoints, summary),
        )
        for route, checkpoints, summary in per_route
    )
    unevaluated = sum(1 for r in results if r.summary is None)
    unsafe = sum(1 for r in results if r.summary is not None and not r.summary.is_safe)
    recommended = recommendation.recommended if recommendation else None
    weather_status, weather_note = _weather_status([c for r in results for c in r.checkpoints])

    return RouteEvaluation(
        candidates=candidates,
        routes=results,
        recommended_route_id=recommended.route_id if recommended else None,
        ranking=tuple(r.summary.route_id for r in recommendation.ranked_safe_routes)
        if recommendation
        else (),
        message=_message(
            recommendation.message if recommended else None,
            recommended.route_id if recommended else None,
            unevaluated,
            unsafe,
            len(results),
        ),
        weather_status=weather_status,
        weather_note=weather_note,
        recommendation_status=_recommendation_status(recommended is not None, unevaluated),
    )
