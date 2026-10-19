"""Distance-weighted route risk summaries.

Checkpoints are sample points, not road segments. Each checkpoint is assigned
the route miles closer to it than to any other checkpoint: half the gap to its
previous checkpoint plus half the gap to its next one (the first and last
checkpoints only get the inner half). Every mile is counted exactly once and
the segment lengths sum to the analyzed distance.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from risk.engine import CheckpointRisk
from risk.levels import RiskLevel, risk_score

# Allowed mismatch between the checkpoint span and the route's endpoints.
DISTANCE_TOLERANCE_MILES = 0.01


@dataclass(frozen=True)
class RouteCheckpoint:
    """A checkpoint's cumulative distance from the origin and its assessed risk."""

    distance_miles: float
    risk: CheckpointRisk


@dataclass(frozen=True)
class RiskSegment:
    """Stretch of road whose conditions are represented by one checkpoint."""

    start_miles: float
    end_miles: float
    level: RiskLevel

    @property
    def length_miles(self) -> float:
        return self.end_miles - self.start_miles


@dataclass(frozen=True)
class RouteRiskSummary:
    """Route-level risk figures used for ranking and display.

    `average_risk_score` is None when the route contains No Travel conditions,
    so an unsafe route is never represented by a deceptively low average.
    """

    route_id: str
    total_distance_miles: float
    duration_seconds: float
    severe_miles: float
    high_miles: float
    no_travel_miles: float
    average_risk_score: float | None
    has_no_travel: bool
    segments: tuple[RiskSegment, ...]

    @property
    def is_safe(self) -> bool:
        return not self.has_no_travel


def _require_positive_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number, got {value}")
    return float(value)


def build_segments(checkpoints: Sequence[RouteCheckpoint]) -> tuple[RiskSegment, ...]:
    """Split the checkpoint span into one segment per checkpoint at the gap midpoints."""
    distances = [checkpoint.distance_miles for checkpoint in checkpoints]
    boundaries = (
        [distances[0]]
        + [(previous + current) / 2 for previous, current in zip(distances, distances[1:])]
        + [distances[-1]]
    )
    return tuple(
        RiskSegment(start_miles=start, end_miles=end, level=checkpoint.risk.overall)
        for checkpoint, start, end in zip(checkpoints, boundaries, boundaries[1:])
    )


def _validate_checkpoints(
    checkpoints: Sequence[RouteCheckpoint], total_distance_miles: float
) -> None:
    if len(checkpoints) < 2:
        raise ValueError("At least two checkpoints (origin and destination) are required")
    distances = [checkpoint.distance_miles for checkpoint in checkpoints]
    for distance in distances:
        if isinstance(distance, bool) or not isinstance(distance, (int, float)):
            raise TypeError("Checkpoint distances must be numbers")
        if not math.isfinite(distance):
            raise ValueError(f"Checkpoint distance must be finite, got {distance}")
    if any(current <= previous for previous, current in zip(distances, distances[1:])):
        raise ValueError("Checkpoint distances must be strictly increasing")
    if abs(distances[0]) > DISTANCE_TOLERANCE_MILES:
        raise ValueError(f"First checkpoint must be at the origin, got {distances[0]} miles")
    if abs(distances[-1] - total_distance_miles) > DISTANCE_TOLERANCE_MILES:
        raise ValueError(
            f"Last checkpoint ({distances[-1]} miles) must match the route distance "
            f"({total_distance_miles} miles)"
        )


def _miles_at(segments: Sequence[RiskSegment], level: RiskLevel) -> float:
    return math.fsum(segment.length_miles for segment in segments if segment.level == level)


def summarize_route(
    route_id: str,
    checkpoints: Sequence[RouteCheckpoint],
    total_distance_miles: float,
    duration_seconds: float,
) -> RouteRiskSummary:
    """Build a distance-weighted risk summary for one route.

    Checkpoints must be ordered by distance, start at the origin and end at the
    destination. Raises ValueError/TypeError for invalid distances or duration.
    """
    total_distance_miles = _require_positive_finite(total_distance_miles, "total_distance_miles")
    duration_seconds = _require_positive_finite(duration_seconds, "duration_seconds")
    _validate_checkpoints(checkpoints, total_distance_miles)

    segments = build_segments(checkpoints)
    analyzed_miles = math.fsum(segment.length_miles for segment in segments)
    span_miles = checkpoints[-1].distance_miles - checkpoints[0].distance_miles
    assert math.isclose(analyzed_miles, span_miles, rel_tol=1e-9), "segments must cover the span"

    has_no_travel = any(segment.level == RiskLevel.NO_TRAVEL for segment in segments)
    average_risk_score = None
    if not has_no_travel:
        weighted = math.fsum(risk_score(s.level) * s.length_miles for s in segments)
        average_risk_score = weighted / analyzed_miles

    return RouteRiskSummary(
        route_id=route_id,
        total_distance_miles=total_distance_miles,
        duration_seconds=duration_seconds,
        severe_miles=_miles_at(segments, RiskLevel.SEVERE),
        high_miles=_miles_at(segments, RiskLevel.HIGH),
        no_travel_miles=_miles_at(segments, RiskLevel.NO_TRAVEL),
        average_risk_score=average_risk_score,
        has_no_travel=has_no_travel,
        segments=segments,
    )
