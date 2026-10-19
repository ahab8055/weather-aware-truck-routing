import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from routes import views
from routes.tests.ors_fixtures import (
    FAKE_API_KEY,
    directions_payload,
    make_client,
    ors_error,
)
from routes.tests.test_api import ALTERNATIVES, VALID_REQUEST, ors_handler
from weather.tests.open_meteo_fixtures import forecast_handler, make_weather_client

URL = reverse("route-evaluate")


def departure_in(delta: timedelta) -> str:
    # Relative to the real clock so forecast-horizon checks stay valid over time.
    moment = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + delta
    return moment.isoformat()


def request_body(**overrides):
    return {**VALID_REQUEST, "departure_time": departure_in(timedelta(days=1)), **overrides}


@pytest.fixture
def services(monkeypatch):
    def install(directions=None, weather=None, api_key=FAKE_API_KEY, weather_calls=None):
        directions = directions or [httpx.Response(200, json=directions_payload(*ALTERNATIVES))]
        monkeypatch.setattr(
            views, "build_ors_client", lambda: make_client(ors_handler(directions), api_key)
        )
        handler = weather or forecast_handler(calls=weather_calls)
        monkeypatch.setattr(views, "build_weather_client", lambda: make_weather_client(handler))

    return install


def post(payload):
    return APIClient().post(URL, payload, format="json")


def test_full_evaluation_response(services):
    weather_calls = []
    services(weather_calls=weather_calls)

    response = post(request_body())

    assert response.status_code == 200
    body = response.json()
    assert body["route_count"] == 3
    assert body["weather_status"] == "complete"
    assert body["weather_note"] is None
    # Calm everywhere: equal risk, so the shortest duration (route-2, 4000 s) wins.
    assert body["recommended_route_id"] == "route-2"
    assert body["safe_route_available"] is True
    assert body["ranking"] == ["route-2", "route-1", "route-3"]
    assert body["recommendation_message"] == "Recommended route: route-2."
    assert body["recommendation_status"] == "recommended"
    assert body["comparison_conclusive"] is True
    assert body["not_recommended"] == []

    route = body["routes"][0]
    assert route["evaluation_status"] == "evaluated"
    assert route["rank"] == 2
    assert route["summary"] == {
        "severe_miles": 0.0,
        "high_miles": 0.0,
        "no_travel_miles": 0.0,
        "average_risk_score": 0.0,
        "total_distance_miles": 70.0,
        "duration_seconds": 4200.0,
        "has_no_travel": False,
        "is_safe": True,
    }
    checkpoint = route["checkpoints"][0]
    assert set(checkpoint) == {
        "index",
        "distance_miles",
        "latitude",
        "longitude",
        "elapsed_seconds",
        "eta",
        "weather",
        "risk",
    }
    assert checkpoint["weather"]["status"] == "available"
    assert checkpoint["weather"]["wind_speed_mph"] == 8.0
    assert checkpoint["weather"]["rain_in_per_hr"] == 0.0
    assert checkpoint["weather"]["snowfall_in_per_hr"] == 0.0
    assert checkpoint["weather"]["forecast_time"].endswith("+00:00")
    assert checkpoint["risk"] == {
        "wind": "low",
        "rain": "low",
        "snow": "low",
        "base": "low",
        "overall": "low",
        "load_restriction": "none",
    }
    # All three routes share one batched Open-Meteo request.
    assert len(weather_calls) == 1


def test_storm_with_heavy_load_makes_routes_unsafe(services):
    services(weather=forecast_handler(lambda lat, lng, t: (48.0, 0.0, 0.0)))

    body = post(request_body(load_weight_lbs=36_000)).json()

    assert body["recommended_route_id"] is None
    assert body["safe_route_available"] is False
    assert body["recommendation_status"] == "no_safe_route"
    assert body["comparison_conclusive"] is True
    assert body["ranking"] == []
    assert "No safe route available" in body["recommendation_message"]
    assert [entry["route_id"] for entry in body["not_recommended"]] == ["route-1", "route-2", "route-3"]
    assert body["not_recommended"][0]["reasons"][0]["code"] == "no_travel"
    risk = body["routes"][0]["checkpoints"][1]["risk"]
    assert risk["base"] == "severe"
    assert risk["overall"] == "no_travel"
    assert risk["load_restriction"] == "heavy_load_wind_no_travel"
    assert body["routes"][0]["summary"]["average_risk_score"] is None


def test_weather_provider_failure_returns_explicit_unavailable_status(services, caplog):
    caplog.set_level(logging.DEBUG)
    services(weather=lambda request: httpx.Response(500, json={"error": True, "reason": "db down"}))

    response = post(request_body())

    assert response.status_code == 200
    body = response.json()
    assert body["weather_status"] == "unavailable"
    assert body["recommended_route_id"] is None
    assert body["recommendation_status"] == "inconclusive"
    assert body["comparison_conclusive"] is False
    checkpoint = body["routes"][0]["checkpoints"][0]
    assert checkpoint["weather"] == {
        "status": "unavailable",
        "reason": "provider_error",
        "message": "The weather provider is unavailable.",
        "forecast_time": None,
        "wind_speed_mph": None,
        "rain_in_per_hr": None,
        "snowfall_in_per_hr": None,
    }
    assert checkpoint["risk"] is None
    assert body["routes"][0]["summary"] is None
    assert body["routes"][0]["evaluation_status"] == "weather_unavailable"
    assert "db down" not in response.content.decode()


def test_trip_beyond_forecast_horizon_is_flagged(services):
    weather_calls = []
    services(weather_calls=weather_calls)

    body = post(request_body(departure_time=departure_in(timedelta(days=20)))).json()

    assert weather_calls == []
    assert body["weather_status"] == "unavailable"
    assert "outside forecast coverage" in body["weather_note"]
    assert body["routes"][0]["checkpoints"][0]["weather"]["reason"] == "outside_forecast_coverage"
    assert body["recommended_route_id"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("origin", ""),
        ("departure_time", "2026-10-19T08:00:00"),
        ("checkpoint_interval_miles", 15),
        ("load_weight_lbs", 0),
        ("load_weight_lbs", "NaN"),
    ],
)
def test_validation_errors_return_400(services, field, value):
    services()

    response = post(request_body(**{field: value}))

    assert response.status_code == 400
    assert field in response.json()


def test_routing_errors_are_sanitized(services):
    services(directions=[ors_error(404, 2010, f"point not found {FAKE_API_KEY}")])

    response = post(request_body())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "route_not_found"
    assert FAKE_API_KEY not in response.content.decode()


@pytest.mark.parametrize(("point_index", "field", "query"), [(0, "origin", "Waco, TX"), (1, "destination", "Temple, TX")])
def test_unroutable_endpoint_names_the_field(services, point_index, field, query):
    # Live case: "Los Angeles County, CA, USA" geocodes to a forest centroid with no truck road nearby.
    message = f"Could not find routable point within a radius of 350.0 meters of specified coordinate {point_index}: 1 2."
    services(directions=[ors_error(404, 2010, message)])

    response = post(request_body())

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "location_not_routable"
    assert error["field"] == field
    assert error["query"] == query
    assert f'The {field} "{query}" is not near a road trucks can use.' in error["message"]


def test_missing_ors_key_returns_503(services):
    services(api_key="")

    response = post(request_body())

    assert response.status_code == 503


def test_get_is_not_allowed():
    assert APIClient().get(URL).status_code == 405
