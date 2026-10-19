import logging

import httpx
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from routes import views
from routes.tests.ors_fixtures import FAKE_API_KEY, geocode_feature, geocode_payload, make_client

URL = reverse("route-location-suggest")


@pytest.fixture
def ors(monkeypatch):
    def install(handler, api_key=FAKE_API_KEY):
        monkeypatch.setattr(views, "build_ors_client", lambda: make_client(handler, api_key))

    return install


def suggest(q=None):
    return APIClient().get(URL, {} if q is None else {"q": q})


def test_returns_deduplicated_suggestions(ors):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            json=geocode_payload(
                geocode_feature("Houston, TX, USA", 29.7847531, -95.3614165),
                geocode_feature("Houston, TX, USA", 29.76, -95.37),
                geocode_feature("Houston, MN, USA", 43.759028, -91.570956),
            ),
        )

    ors(handler)
    response = suggest("Hous")

    assert response.status_code == 200
    assert response.json() == {
        "query": "Hous",
        "suggestions": [
            {"label": "Houston, TX, USA", "latitude": 29.784753, "longitude": -95.361417},
            {"label": "Houston, MN, USA", "latitude": 43.759028, "longitude": -91.570956},
        ],
    }
    assert calls[0].url.path == "/geocode/autocomplete"


def test_at_most_five_suggestions(ors):
    features = [geocode_feature(f"Place {i}, TX, USA", 30 + i / 10, -97) for i in range(8)]
    ors(lambda request: httpx.Response(200, json=geocode_payload(*features)))

    assert len(suggest("Place").json()["suggestions"]) == 5


@pytest.mark.parametrize("q", ["", "Ho", "  "])
def test_short_queries_return_nothing_without_calling_the_provider(ors, q):
    calls = []
    ors(lambda request: calls.append(request) or httpx.Response(200, json=geocode_payload()))

    response = suggest(q)

    if q.strip():
        assert response.status_code == 200
        assert response.json()["suggestions"] == []
    else:
        assert response.status_code == 400
    assert calls == []


def test_missing_and_overlong_queries_are_rejected(ors):
    ors(lambda request: httpx.Response(200, json=geocode_payload()))

    assert suggest().status_code == 400
    assert suggest("x" * 201).status_code == 400


def test_missing_key_returns_503(ors):
    ors(lambda request: httpx.Response(200, json=geocode_payload()), api_key="")

    response = suggest("Hous")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "routing_not_configured"


@pytest.mark.parametrize(
    ("handler", "status", "code"),
    [
        (lambda r: httpx.Response(500, text=f"boom {FAKE_API_KEY}"), 502, "routing_unavailable"),
        (lambda r: httpx.Response(429), 502, "routing_rate_limited"),
        (lambda r: httpx.Response(200, text=f"not json {FAKE_API_KEY}"), 502, "invalid_route_data"),
    ],
)
def test_provider_failures_are_sanitized(ors, caplog, handler, status, code):
    caplog.set_level(logging.DEBUG)
    ors(handler)

    response = suggest("Hous")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert FAKE_API_KEY not in response.content.decode()
    assert FAKE_API_KEY not in caplog.text


def test_post_is_not_allowed():
    assert APIClient().post(URL, {"q": "Hous"}).status_code == 405
