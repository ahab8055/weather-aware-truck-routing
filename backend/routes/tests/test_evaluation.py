from datetime import UTC, datetime, timedelta, timezone

import pytest

from risk.engine import LoadRestriction
from risk.levels import RiskLevel
from risk.recommendation import NO_SAFE_ROUTE_MESSAGE
from routes.checkpoints import generate_checkpoints
from routes.evaluation import (
    EVALUATED,
    INCONCLUSIVE,
    NO_SAFE_ROUTE,
    PROVISIONAL,
    RECOMMENDED,
    WEATHER_UNAVAILABLE,
    evaluate_routes,
)
from routes.geocoding import ResolvedLocation
from routes.geometry import cumulative_distances
from routes.services import RouteCandidate, RouteCandidates
from weather.errors import weather_unavailable
from weather.forecast import MISSING_VALUES, OUTSIDE_COVERAGE, NormalizedWeather
from weather.open_meteo import HourlySeries

CENTRAL = timezone(timedelta(hours=-5))
NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
DEPARTURE = datetime(2026, 10, 19, 8, 0, tzinfo=CENTRAL)  # 13:00 UTC

ORIGIN = ResolvedLocation("Waco, TX", "Waco, TX, USA", 30.0, -97.0)
DESTINATION = ResolvedLocation("Temple, TX", "Temple, TX, USA", 31.0, -97.0)

# Straight north along -97 and a detour east through (30.5, -96.5); same endpoints.
WEST = ((30.0, -97.0), (30.5, -97.0), (31.0, -97.0))
EAST = ((30.0, -97.0), (30.5, -96.5), (31.0, -97.0))


def length(geometry):
    return cumulative_distances(geometry)[-1]


def candidate(route_id, order, geometry, duration, departure=DEPARTURE, interval=25):
    distance = length(geometry)
    return RouteCandidate(
        id=route_id,
        provider_order=order,
        distance_miles=distance,
        duration_seconds=duration,
        geometry=geometry,
        checkpoints=generate_checkpoints(geometry, distance, duration, departure, interval),
        origin=ORIGIN,
        destination=DESTINATION,
        departure_time=departure,
        checkpoint_interval_miles=interval,
        load_weight_lbs=0,
    )


def candidates(*routes, load=20_000, departure=DEPARTURE):
    return RouteCandidates(
        origin=ORIGIN,
        destination=DESTINATION,
        departure_time=departure,
        checkpoint_interval_miles=25,
        load_weight_lbs=load,
        requested_route_count=3,
        routes=routes,
        alternatives_note=None,
    )


class FakeForecasts:
    """Stands in for OpenMeteoClient; `conditions(lat, lng, time)` -> (wind, rain, snow)."""

    def __init__(self, conditions=lambda lat, lng, t: (8.0, 0.0, 0.0), error=None):
        self.conditions = conditions
        self.error = error
        self.calls = []

    def fetch_hourly(self, locations, start, end):
        self.calls.append((list(locations), start, end))
        if self.error:
            return [self.error] * len(locations)
        times = []
        moment = start
        while moment <= end:
            times.append(moment)
            moment += timedelta(hours=1)
        results = []
        for lat, lng in locations:
            values = [self.conditions(lat, lng, t) for t in times]
            wind, rain, snow = (tuple(column) for column in zip(*values))
            results.append(HourlySeries(tuple(times), wind, rain, snow))
        return results


def windy_north(lat, lng, t):
    """47 mph wind (Severe) north of 30.5 N, calm elsewhere."""
    return (47.0, 0.0, 0.0) if lat >= 30.5 else (8.0, 0.0, 0.0)


def windy_west_middle(lat, lng, t):
    """Severe wind only on the straight western road's middle stretch."""
    return (47.0, 0.0, 0.0) if lng < -96.9 and 30.2 < lat < 30.9 else (8.0, 0.0, 0.0)


def test_checkpoint_weather_and_risk_use_eta_forecast():
    route = candidate("route-1", 0, WEST, duration=3_600)
    evaluation = evaluate_routes(candidates(route), FakeForecasts(windy_north), now=NOW)

    (result,) = evaluation.routes
    first, second, third, last = result.checkpoints
    assert first.weather == NormalizedWeather(datetime(2026, 10, 19, 13, tzinfo=UTC), 8.0, 0.0, 0.0)
    # 25 of 69.09 mi at 1 h total -> ETA 13:21:42 UTC -> nearest hour 13:00.
    assert second.weather.forecast_time == datetime(2026, 10, 19, 13, tzinfo=UTC)
    # 50 mi -> ETA 13:43:25 UTC -> 14:00.
    assert third.weather.forecast_time == datetime(2026, 10, 19, 14, tzinfo=UTC)
    assert last.weather.forecast_time == datetime(2026, 10, 19, 14, tzinfo=UTC)
    assert [c.risk.overall for c in result.checkpoints] == [
        RiskLevel.LOW,
        RiskLevel.LOW,
        RiskLevel.SEVERE,
        RiskLevel.SEVERE,
    ]
    assert third.risk.wind is RiskLevel.SEVERE


def test_eta_not_departure_time_selects_the_forecast_hour():
    # Severe wind only from 15:00 UTC; departure is 13:00 UTC, arrival 16:00 UTC.
    def storm_later(lat, lng, t):
        return (50.0, 0.0, 0.0) if t >= datetime(2026, 10, 19, 15, tzinfo=UTC) else (5.0, 0.0, 0.0)

    route = candidate("route-1", 0, WEST, duration=3 * 3_600)
    (result,) = evaluate_routes(candidates(route), FakeForecasts(storm_later), now=NOW).routes

    assert [c.risk.overall for c in result.checkpoints] == [
        RiskLevel.LOW,  # 13:00
        RiskLevel.LOW,  # ETA 14:05 -> 14:00
        RiskLevel.SEVERE,  # ETA 15:10 -> 15:00
        RiskLevel.SEVERE,  # ETA 16:00
    ]


def test_route_summary_is_distance_weighted():
    route = candidate("route-1", 0, WEST, duration=3_600)
    evaluation = evaluate_routes(candidates(route), FakeForecasts(windy_north), now=NOW)

    summary = evaluation.routes[0].summary
    total = length(WEST)
    # Checkpoints at 0, 25, 50, total; Severe from the 25/50 midpoint (37.5) to the end.
    assert summary.severe_miles == pytest.approx(total - 37.5)
    assert summary.high_miles == 0
    assert summary.average_risk_score == pytest.approx(3 * (total - 37.5) / total)
    assert summary.total_distance_miles == pytest.approx(total)
    assert summary.duration_seconds == 3_600
    assert evaluation.recommended_route_id == "route-1"
    assert evaluation.weather_status == "complete"
    assert evaluation.weather_note is None


def test_load_rule_escalates_to_no_travel_and_route_is_not_recommended():
    route = candidate("route-1", 0, WEST, duration=3_600)
    evaluation = evaluate_routes(candidates(route, load=35_000), FakeForecasts(windy_north), now=NOW)

    (result,) = evaluation.routes
    escalated = result.checkpoints[2].risk
    assert escalated.base is RiskLevel.SEVERE
    assert escalated.overall is RiskLevel.NO_TRAVEL
    assert escalated.load_restriction is LoadRestriction.HEAVY_LOAD_WIND_NO_TRAVEL
    assert result.summary.has_no_travel
    assert result.rank is None
    assert evaluation.recommended_route_id is None
    assert not evaluation.safe_route_available
    assert evaluation.message == NO_SAFE_ROUTE_MESSAGE
    assert [r.code for r in result.not_recommended_reasons] == ["no_travel"]


def test_rain_and_snow_classifications_are_preserved():
    def wet(lat, lng, t):
        return (10.0, 0.3, 2.5) if lat >= 30.5 else (10.0, 0.12, 0.0)

    route = candidate("route-1", 0, WEST, duration=3_600)
    (result,) = evaluate_routes(candidates(route), FakeForecasts(wet), now=NOW).routes

    first_risk, last_risk = result.checkpoints[0].risk, result.checkpoints[-1].risk
    assert (first_risk.wind, first_risk.rain, first_risk.snow) == (
        RiskLevel.LOW,
        RiskLevel.MODERATE,
        RiskLevel.LOW,
    )
    assert (last_risk.rain, last_risk.snow, last_risk.overall) == (
        RiskLevel.HIGH,
        RiskLevel.SEVERE,
        RiskLevel.SEVERE,
    )


def test_safer_longer_route_beats_faster_route_with_severe_miles():
    west = candidate("route-1", 0, WEST, duration=3_600)
    east = candidate("route-2", 1, EAST, duration=5_400)
    evaluation = evaluate_routes(candidates(west, east), FakeForecasts(windy_west_middle), now=NOW)

    assert evaluation.recommended_route_id == "route-2"
    assert evaluation.ranking == ("route-2", "route-1")
    assert [r.rank for r in evaluation.routes] == [2, 1]
    assert evaluation.routes[0].summary.severe_miles > 0
    assert evaluation.routes[1].summary.severe_miles == 0
    assert evaluation.message == "Recommended route: route-2."


def test_exact_ties_keep_provider_order():
    first = candidate("route-1", 0, WEST, duration=3_600)
    second = candidate("route-2", 1, WEST, duration=3_600)

    evaluation = evaluate_routes(candidates(first, second), FakeForecasts(), now=NOW)

    assert evaluation.ranking == ("route-1", "route-2")


def test_shared_and_duplicate_checkpoints_are_fetched_once():
    west = candidate("route-1", 0, WEST, duration=3_600)
    east = candidate("route-2", 1, EAST, duration=5_400)
    twin = candidate("route-3", 2, WEST, duration=3_700)
    source = FakeForecasts()

    evaluate_routes(candidates(west, east, twin), source, now=NOW)

    assert len(source.calls) == 1
    locations, start, end = source.calls[0]
    all_checkpoints = west.checkpoints + east.checkpoints + twin.checkpoints
    assert length(EAST) > 75
    assert len(all_checkpoints) == 4 + 5 + 4
    # Shared origin/destination and the identical twin route collapse: origin, destination,
    # WEST's 2 interior points and EAST's 3 interior points.
    assert len(locations) == len(set(locations)) == 7
    assert start == datetime(2026, 10, 19, 13, tzinfo=UTC)
    assert end == datetime(2026, 10, 19, 15, tzinfo=UTC)


def test_missing_weather_route_is_never_recommended_or_treated_as_safe():
    def gap_on_west(lat, lng, t):
        return (None, 0.0, 0.0) if lng < -96.9 and 30.2 < lat < 30.9 else (8.0, 0.0, 0.0)

    west = candidate("route-1", 0, WEST, duration=3_000)
    east = candidate("route-2", 1, EAST, duration=5_400)
    evaluation = evaluate_routes(candidates(west, east), FakeForecasts(gap_on_west), now=NOW)

    west_result, east_result = evaluation.routes
    assert west_result.status == WEATHER_UNAVAILABLE
    assert west_result.summary is None
    assert west_result.rank is None
    missing = [c for c in west_result.checkpoints if c.risk is None]
    assert len(missing) == 2
    assert all(c.weather.reason == MISSING_VALUES for c in missing)
    assert [r.code for r in west_result.not_recommended_reasons] == ["weather_unavailable"]
    assert "2 of 4 checkpoints" in west_result.not_recommended_reasons[0].message

    assert east_result.status == EVALUATED
    assert evaluation.recommended_route_id == "route-2"
    assert evaluation.ranking == ("route-2",)
    assert evaluation.weather_status == "partial"
    assert "1 of 2 route(s) could not be fully evaluated" in evaluation.message


def test_weather_provider_down_means_no_recommendation():
    route = candidate("route-1", 0, WEST, duration=3_600)
    evaluation = evaluate_routes(
        candidates(route), FakeForecasts(error=weather_unavailable()), now=NOW
    )

    (result,) = evaluation.routes
    assert all(c.weather.reason == "provider_error" for c in result.checkpoints)
    assert all(c.risk is None for c in result.checkpoints)
    assert evaluation.recommended_route_id is None
    assert evaluation.weather_status == "unavailable"
    assert evaluation.message.startswith("No safe route can be confirmed")


def test_unavailable_and_no_travel_routes_both_reported():
    def stormy_west_missing_east(lat, lng, t):
        if lng > -96.9:
            return (None, None, None)
        return (60.0, 0.0, 0.0)

    west = candidate("route-1", 0, WEST, duration=3_600)
    east = candidate("route-2", 1, EAST, duration=5_400)
    evaluation = evaluate_routes(
        candidates(west, east), FakeForecasts(stormy_west_missing_east), now=NOW
    )

    assert evaluation.recommended_route_id is None
    assert evaluation.message == (
        "No safe route can be confirmed: weather forecasts are unavailable for 1 of 2 route(s), "
        "and the other 1 contain No Travel conditions."
    )
    east_reasons = [r.code for r in evaluation.routes[1].not_recommended_reasons]
    assert east_reasons == ["no_travel", "weather_unavailable"]


def test_trip_beyond_forecast_horizon_makes_no_request():
    departure = NOW + timedelta(days=20)
    route = candidate("route-1", 0, WEST, duration=3_600, departure=departure)
    source = FakeForecasts()

    evaluation = evaluate_routes(candidates(route, departure=departure), source, now=NOW)

    assert source.calls == []
    assert all(c.weather.reason == OUTSIDE_COVERAGE for c in evaluation.routes[0].checkpoints)
    assert evaluation.weather_status == "unavailable"
    assert "outside forecast coverage" in evaluation.weather_note
    assert evaluation.recommended_route_id is None


def test_trip_crossing_forecast_horizon_marks_later_checkpoints():
    # Forecasts end at 2026-11-02 23:00 UTC for NOW = 2026-10-18.
    departure = datetime(2026, 11, 2, 22, tzinfo=UTC)
    route = candidate("route-1", 0, WEST, duration=3 * 3_600, departure=departure)
    source = FakeForecasts()

    evaluation = evaluate_routes(candidates(route, departure=departure), source, now=NOW)

    _, start, end = source.calls[0]
    assert (start, end) == (departure, datetime(2026, 11, 2, 23, tzinfo=UTC))
    checkpoints = evaluation.routes[0].checkpoints
    assert [c.risk is not None for c in checkpoints] == [True, True, False, False]
    assert all(c.weather.reason == OUTSIDE_COVERAGE for c in checkpoints[2:])
    assert evaluation.routes[0].status == WEATHER_UNAVAILABLE
    assert evaluation.weather_status == "partial"
    assert evaluation.recommended_route_id is None


# --- Recommendation status: audit scenarios -------------------------------------------


def test_status_all_routes_evaluated_and_safe_is_conclusive_recommendation():
    west = candidate("route-1", 0, WEST, duration=3_600)
    east = candidate("route-2", 1, EAST, duration=5_400)

    evaluation = evaluate_routes(candidates(west, east), FakeForecasts(), now=NOW)

    assert evaluation.recommendation_status == RECOMMENDED
    assert evaluation.comparison_conclusive
    assert evaluation.recommended_route_id == "route-1"
    assert evaluation.message == "Recommended route: route-1."


def test_status_one_no_travel_route_recommends_the_safe_one():
    def storm_on_west(lat, lng, t):
        return (60.0, 0.0, 0.0) if lng < -96.9 and 30.2 < lat < 30.9 else (8.0, 0.0, 0.0)

    west = candidate("route-1", 0, WEST, duration=3_600)
    east = candidate("route-2", 1, EAST, duration=5_400)
    evaluation = evaluate_routes(candidates(west, east), FakeForecasts(storm_on_west), now=NOW)

    assert evaluation.recommendation_status == RECOMMENDED
    assert evaluation.comparison_conclusive
    assert evaluation.recommended_route_id == "route-2"
    assert evaluation.routes[0].summary.has_no_travel
    assert [r.code for r in evaluation.routes[0].not_recommended_reasons] == ["no_travel"]


def test_status_every_route_unsafe_is_conclusive_no_safe_route():
    west = candidate("route-1", 0, WEST, duration=3_600)
    east = candidate("route-2", 1, EAST, duration=5_400)
    evaluation = evaluate_routes(
        candidates(west, east), FakeForecasts(lambda lat, lng, t: (60.0, 0.0, 0.0)), now=NOW
    )

    assert evaluation.recommendation_status == NO_SAFE_ROUTE
    assert evaluation.comparison_conclusive
    assert evaluation.recommended_route_id is None
    assert evaluation.message == NO_SAFE_ROUTE_MESSAGE


def test_status_partial_weather_is_provisional_and_inconclusive():
    def gap_on_west(lat, lng, t):
        return (None, 0.0, 0.0) if lng < -96.9 and 30.2 < lat < 30.9 else (8.0, 0.0, 0.0)

    west = candidate("route-1", 0, WEST, duration=3_000)
    east = candidate("route-2", 1, EAST, duration=5_400)
    evaluation = evaluate_routes(candidates(west, east), FakeForecasts(gap_on_west), now=NOW)

    assert evaluation.recommendation_status == PROVISIONAL
    assert not evaluation.comparison_conclusive
    assert evaluation.recommended_route_id == "route-2"
    assert evaluation.message == (
        "Provisional: route-2 is the safest of the fully evaluated routes. 1 of 2 route(s) could "
        "not be fully evaluated because weather forecasts were unavailable, so the overall "
        "comparison is inconclusive."
    )
    # The incomplete route never gets a safe classification.
    assert evaluation.routes[0].summary is None
    assert evaluation.routes[0].status == WEATHER_UNAVAILABLE


def test_status_provider_failure_is_inconclusive():
    route = candidate("route-1", 0, WEST, duration=3_600)
    evaluation = evaluate_routes(candidates(route), FakeForecasts(error=weather_unavailable()), now=NOW)

    assert evaluation.recommendation_status == INCONCLUSIVE
    assert not evaluation.comparison_conclusive
    assert not evaluation.safe_route_available


def test_status_checkpoints_outside_coverage_is_inconclusive():
    departure = datetime(2026, 11, 2, 22, tzinfo=UTC)
    route = candidate("route-1", 0, WEST, duration=3 * 3_600, departure=departure)
    evaluation = evaluate_routes(candidates(route, departure=departure), FakeForecasts(), now=NOW)

    assert evaluation.recommendation_status == INCONCLUSIVE
    assert not evaluation.comparison_conclusive
    assert evaluation.recommended_route_id is None
