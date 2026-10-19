"""Request validation and response shaping for the routes API."""

import math
from collections.abc import Sequence
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from risk.engine import CheckpointRisk
from risk.levels import RiskLevel
from risk.summary import RouteRiskSummary
from routes.checkpoints import ALLOWED_INTERVALS_MILES, Checkpoint
from routes.errors import RoutingError
from routes.evaluation import RouteEvaluation, RouteEvaluationResult
from routes.geocoding import ResolvedLocation
from routes.ors import GeocodeCandidate
from routes.services import RouteCandidate, RouteCandidates
from weather.forecast import NormalizedWeather, WeatherUnavailable

MILES_DECIMALS = 3
SECONDS_DECIMALS = 1
COORDINATE_DECIMALS = 6


class AwareDateTimeField(serializers.DateTimeField):
    """ISO 8601 datetime that must carry a UTC offset; the given offset is preserved."""

    default_error_messages = {
        "naive": "Include a timezone offset, e.g. 2026-10-19T08:00:00-05:00 or ...Z.",
    }

    def enforce_timezone(self, value):
        if timezone.is_naive(value):
            self.fail("naive")
        return value


class PositiveFiniteFloatField(serializers.FloatField):
    default_error_messages = {
        "not_positive_finite": "Must be a positive, finite number.",
    }

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        value = super().to_internal_value(data)
        if not math.isfinite(value) or value <= 0:
            self.fail("not_positive_finite")
        return value


class LocationSuggestionQuerySerializer(serializers.Serializer):
    q = serializers.CharField(max_length=200)


class RouteCandidatesRequestSerializer(serializers.Serializer):
    origin = serializers.CharField(max_length=200)
    destination = serializers.CharField(max_length=200)
    departure_time = AwareDateTimeField()
    checkpoint_interval_miles = serializers.ChoiceField(choices=ALLOWED_INTERVALS_MILES)
    load_weight_lbs = PositiveFiniteFloatField()


def _location(location: ResolvedLocation) -> dict[str, Any]:
    return {
        "query": location.query,
        "label": location.label,
        "latitude": round(location.latitude, COORDINATE_DECIMALS),
        "longitude": round(location.longitude, COORDINATE_DECIMALS),
    }


def _checkpoint(checkpoint: Checkpoint) -> dict[str, Any]:
    return {
        "index": checkpoint.index,
        "distance_miles": round(checkpoint.distance_miles, MILES_DECIMALS),
        "latitude": round(checkpoint.latitude, COORDINATE_DECIMALS),
        "longitude": round(checkpoint.longitude, COORDINATE_DECIMALS),
        "elapsed_seconds": round(checkpoint.elapsed_seconds, SECONDS_DECIMALS),
        "eta": checkpoint.eta.isoformat(),
    }


def _route(route: RouteCandidate) -> dict[str, Any]:
    return {
        "id": route.id,
        "provider_order": route.provider_order,
        "distance_miles": round(route.distance_miles, MILES_DECIMALS),
        "duration_seconds": round(route.duration_seconds, SECONDS_DECIMALS),
        "geometry": [
            [round(lat, COORDINATE_DECIMALS), round(lng, COORDINATE_DECIMALS)]
            for lat, lng in route.geometry
        ],
        "checkpoints": [_checkpoint(checkpoint) for checkpoint in route.checkpoints],
    }


def serialize_route_candidates(result: RouteCandidates) -> dict[str, Any]:
    """JSON-ready response body. Shared request context appears once at the top level."""
    return {
        "origin": _location(result.origin),
        "destination": _location(result.destination),
        "departure_time": result.departure_time.isoformat(),
        "checkpoint_interval_miles": result.checkpoint_interval_miles,
        "load_weight_lbs": result.load_weight_lbs,
        "requested_route_count": result.requested_route_count,
        "route_count": len(result.routes),
        "alternatives_note": result.alternatives_note,
        "routes": [_route(route) for route in result.routes],
    }


WEATHER_DECIMALS = 3
RISK_SCORE_DECIMALS = 3


def _level(level: RiskLevel) -> str:
    return level.name.lower()


def serialize_weather(weather: NormalizedWeather | WeatherUnavailable) -> dict[str, Any]:
    """Checkpoint `weather` object; shared by route evaluation and the forecast window."""
    if isinstance(weather, WeatherUnavailable):
        return {
            "status": "unavailable",
            "reason": weather.reason,
            "message": weather.message,
            "forecast_time": weather.forecast_time.isoformat() if weather.forecast_time else None,
            "wind_speed_mph": None,
            "rain_in_per_hr": None,
            "snowfall_in_per_hr": None,
        }
    return {
        "status": "available",
        "reason": None,
        "message": None,
        "forecast_time": weather.forecast_time.isoformat(),
        "wind_speed_mph": round(weather.wind_speed_mph, WEATHER_DECIMALS),
        "rain_in_per_hr": round(weather.rain_in_per_hr, WEATHER_DECIMALS),
        "snowfall_in_per_hr": round(weather.snowfall_in_per_hr, WEATHER_DECIMALS),
    }


def serialize_risk(risk: CheckpointRisk | None) -> dict[str, Any] | None:
    """Checkpoint `risk` object (None when weather is unavailable)."""
    if risk is None:
        return None
    return {
        "wind": _level(risk.wind),
        "rain": _level(risk.rain),
        "snow": _level(risk.snow),
        "base": _level(risk.base),
        "overall": _level(risk.overall),
        "load_restriction": risk.load_restriction.value,
    }


def _summary(summary: RouteRiskSummary | None) -> dict[str, Any] | None:
    if summary is None:
        return None
    average = summary.average_risk_score
    return {
        "severe_miles": round(summary.severe_miles, MILES_DECIMALS),
        "high_miles": round(summary.high_miles, MILES_DECIMALS),
        "no_travel_miles": round(summary.no_travel_miles, MILES_DECIMALS),
        "average_risk_score": None if average is None else round(average, RISK_SCORE_DECIMALS),
        "total_distance_miles": round(summary.total_distance_miles, MILES_DECIMALS),
        "duration_seconds": round(summary.duration_seconds, SECONDS_DECIMALS),
        "has_no_travel": summary.has_no_travel,
        "is_safe": summary.is_safe,
    }


def _evaluated_route(result: RouteEvaluationResult) -> dict[str, Any]:
    body = _route(result.candidate)
    body["checkpoints"] = [
        {**_checkpoint(c.checkpoint), "weather": serialize_weather(c.weather), "risk": serialize_risk(c.risk)}
        for c in result.checkpoints
    ]
    body["evaluation_status"] = result.status
    body["rank"] = result.rank
    body["summary"] = _summary(result.summary)
    return body


def serialize_route_evaluation(evaluation: RouteEvaluation) -> dict[str, Any]:
    """Candidates response plus weather, per-checkpoint risk, summaries and the recommendation."""
    body = serialize_route_candidates(evaluation.candidates)
    body.update(
        {
            "weather_status": evaluation.weather_status,
            "weather_note": evaluation.weather_note,
            "recommended_route_id": evaluation.recommended_route_id,
            "safe_route_available": evaluation.safe_route_available,
            "recommendation_status": evaluation.recommendation_status,
            "comparison_conclusive": evaluation.comparison_conclusive,
            "recommendation_message": evaluation.message,
            "ranking": list(evaluation.ranking),
            "not_recommended": [
                {
                    "route_id": result.candidate.id,
                    "reasons": [
                        {"code": reason.code, "message": reason.message}
                        for reason in result.not_recommended_reasons
                    ],
                }
                for result in evaluation.routes
                if result.not_recommended_reasons
            ],
            "routes": [_evaluated_route(result) for result in evaluation.routes],
        }
    )
    return body


def serialize_location_suggestions(query: str, candidates: Sequence[GeocodeCandidate]) -> dict[str, Any]:
    seen: set[str] = set()
    suggestions = []
    for candidate in candidates:
        if candidate.label in seen:
            continue
        seen.add(candidate.label)
        suggestions.append(
            {
                "label": candidate.label,
                "latitude": round(candidate.latitude, COORDINATE_DECIMALS),
                "longitude": round(candidate.longitude, COORDINATE_DECIMALS),
            }
        )
    return {"query": query, "suggestions": suggestions}


def serialize_routing_error(error: RoutingError) -> dict[str, Any]:
    body: dict[str, Any] = {"code": error.code, "message": error.message}
    # `query` and `field` tell the client which input (origin or destination) the error refers to.
    for key in ("query", "field", "candidates"):
        if key in error.details:
            body[key] = error.details[key]
    return {"error": body}
