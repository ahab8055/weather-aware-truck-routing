import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from weather import views
from weather.tests.open_meteo_fixtures import forecast_handler, make_weather_client

URL = reverse("weather-forecast-window")


def departure_in(delta: timedelta) -> str:
    return (datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + delta).isoformat()


def body(**overrides):
    return {
        "locations": [{"latitude": 30.0, "longitude": -97.0}, {"latitude": 31.0, "longitude": -97.0}],
        "departure_time": departure_in(timedelta(days=1)),
        "load_weight_lbs": 42000,
        **overrides,
    }


@pytest.fixture
def weather(monkeypatch):
    def install(handler=None, calls=None):
        handler = handler or forecast_handler(calls=calls)
        monkeypatch.setattr(views, "build_weather_client", lambda: make_weather_client(handler))

    return install


def post(payload):
    return APIClient().post(URL, payload, format="json")


def test_returns_49_slots_per_location(weather):
    calls = []
    weather(calls=calls)

    response = post(body())

    assert response.status_code == 200
    data = response.json()
    assert data["step_hours"] == 1
    assert data["max_offset_hours"] == 48
    assert len(data["slots"]) == 49
    assert data["slots"][0]["offset_hours"] == 0
    assert data["slots"][48]["offset_hours"] == 48
    assert data["slots"][0]["forecast_time"].endswith("+00:00")
    assert [(loc["latitude"], loc["longitude"]) for loc in data["locations"]] == [(30.0, -97.0), (31.0, -97.0)]
    first = data["locations"][0]["observations"][0]
    assert first["weather"]["status"] == "available"
    assert first["weather"]["wind_speed_mph"] == 8.0
    assert first["risk"] == {
        "wind": "low",
        "rain": "low",
        "snow": "low",
        "base": "low",
        "overall": "low",
        "load_restriction": "none",
    }
    assert data["coverage_note"] is None
    assert len(calls) == 1


def test_provider_failure_returns_unavailable_observations(weather, caplog):
    caplog.set_level(logging.DEBUG)
    weather(lambda request: httpx.Response(500, json={"error": True, "reason": "secret upstream detail"}))

    response = post(body())

    assert response.status_code == 200
    observation = response.json()["locations"][0]["observations"][10]
    assert observation["weather"]["status"] == "unavailable"
    assert observation["weather"]["reason"] == "provider_error"
    assert observation["weather"]["wind_speed_mph"] is None
    assert observation["risk"] is None
    assert "secret upstream detail" not in response.content.decode()


def test_beyond_horizon_reports_coverage(weather):
    calls = []
    weather(calls=calls)

    data = post(body(departure_time=departure_in(timedelta(days=30)))).json()

    assert calls == []
    assert data["coverage_note"].startswith("49 of 49 hours")
    assert data["locations"][0]["observations"][0]["weather"]["reason"] == "outside_forecast_coverage"


@pytest.mark.parametrize(
    "overrides",
    [
        {"locations": []},
        {"locations": [{"latitude": 30.0, "longitude": -97.0}] * 301},
        {"locations": [{"latitude": 95.0, "longitude": -97.0}]},
        {"locations": [{"latitude": 30.0, "longitude": -181.0}]},
        {"locations": [{"latitude": "NaN", "longitude": -97.0}]},
        {"locations": [{"latitude": 30.0, "longitude": "Infinity"}]},
        {"locations": [{"latitude": True, "longitude": -97.0}]},
        {"locations": [{"latitude": 30.0}]},
        {"departure_time": "2026-10-20T08:00:00"},
        {"departure_time": "soon"},
        {"load_weight_lbs": 0},
        {"load_weight_lbs": "NaN"},
    ],
)
def test_invalid_requests_return_400(weather, overrides):
    calls = []
    weather(calls=calls)

    response = post(body(**overrides))

    assert response.status_code == 400
    assert set(response.json()) & {"locations", "departure_time", "load_weight_lbs"}
    assert calls == []


def test_does_not_need_or_expose_routing_key(weather, settings):
    settings.ORS_API_KEY = "fake-ors-key-should-not-appear"
    weather()

    response = post(body())

    assert response.status_code == 200
    assert "fake-ors-key-should-not-appear" not in response.content.decode()


def test_get_is_not_allowed():
    assert APIClient().get(URL).status_code == 405
