"""Safe-route filtering and deterministic route ranking.

Safe routes are ranked lexicographically, in the assessment's priority order:
fewest Severe miles, fewest High miles, lowest average risk, shortest duration.
No weighted sum is used, so travel time can never outweigh Severe miles.
Values are rounded before comparison so floating-point noise cannot reorder
routes; remaining exact ties keep the candidates' input order.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from risk.summary import RouteRiskSummary

MILES_DECIMALS = 2
AVERAGE_RISK_DECIMALS = 3

NO_SAFE_ROUTE_MESSAGE = (
    "No safe route available: every candidate route contains No Travel conditions."
)


@dataclass(frozen=True)
class RankedRoute:
    """A safe route and its 1-based rank."""

    rank: int
    summary: RouteRiskSummary


@dataclass(frozen=True)
class RouteRecommendation:
    """Ranking outcome. `recommended` is None when no safe route exists."""

    recommended: RouteRiskSummary | None
    ranked_safe_routes: tuple[RankedRoute, ...]
    unsafe_routes: tuple[RouteRiskSummary, ...]
    message: str

    @property
    def safe_route_available(self) -> bool:
        return self.recommended is not None


def ranking_key(summary: RouteRiskSummary) -> tuple[float, float, float, int]:
    """Comparison key for a safe route; smaller is better."""
    if summary.average_risk_score is None:
        raise ValueError(f"Route {summary.route_id!r} contains No Travel and cannot be ranked")
    return (
        round(summary.severe_miles, MILES_DECIMALS),
        round(summary.high_miles, MILES_DECIMALS),
        round(summary.average_risk_score, AVERAGE_RISK_DECIMALS),
        round(summary.duration_seconds),
    )


def recommend_route(summaries: Sequence[RouteRiskSummary]) -> RouteRecommendation:
    """Exclude routes with No Travel conditions and rank the rest.

    Raises ValueError for an empty candidate list or duplicate route ids.
    """
    if not summaries:
        raise ValueError("At least one candidate route is required")
    route_ids = [summary.route_id for summary in summaries]
    if len(set(route_ids)) != len(route_ids):
        raise ValueError("Route ids must be unique")

    safe = [summary for summary in summaries if summary.is_safe]
    unsafe = tuple(summary for summary in summaries if not summary.is_safe)
    # sorted() is stable, so exact ties keep input order.
    ranked = tuple(
        RankedRoute(rank=index, summary=summary)
        for index, summary in enumerate(sorted(safe, key=ranking_key), start=1)
    )

    if not ranked:
        return RouteRecommendation(
            recommended=None,
            ranked_safe_routes=(),
            unsafe_routes=unsafe,
            message=NO_SAFE_ROUTE_MESSAGE,
        )
    best = ranked[0].summary
    return RouteRecommendation(
        recommended=best,
        ranked_safe_routes=ranked,
        unsafe_routes=unsafe,
        message=f"Recommended route: {best.route_id}.",
    )
