import logging

import httpx
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from routes import views
from routes.tests.ors_fixtures import (
    FAKE_API_KEY,
    MERIDIAN_LNGLAT,
    METERS_PER_MILE,
    directions_payload,
    geocode_feature,
    geocode_payload,
    make_client,
    ors_error,
    request_json,
    route_feature,
)

URL = reverse("route-candidates")

VALID_REQUEST = {
    "origin": "Waco, TX",
    "destination": "Temple, TX",
    "departure_time": "2026-10-19T08:00:00-05:00",
    "checkpoint_interval_miles": 25,
    "load_weight_lbs": 42000,
}

PLACES = {
    "Waco, TX": geocode_feature("Waco, TX, USA", 30.0, -97.0),
    "Temple, TX": geocode_feature("Temple, TX, USA", 31.0, -97.0),
}

# Three alternatives over the same test polyline: 70, 75 and 80 miles.
ALTERNATIVES = [
    route_feature(70 * METERS_PER_MILE, 4_200, MERIDIAN_LNGLAT),
    route_feature(75 * METERS_PER_MILE, 4_000, MERIDIAN_LNGLAT),
    route_feature(80 * METERS_PER_MILE, 4_500, MERIDIAN_LNGLAT),
]


def ors_handler(directions=None, geocode=None, calls=None):
    """Route stubbed requests by path. `directions` may be a list consumed per call."""
    directions_responses = list(directions or [])

    def handler(request):
        if calls is not None:
            calls.append(request)
        if request.url.path == "/geocode/search":
            if geocode is not None:
                return geocode(request)
            feature = PLACES.get(request.url.params["text"])
            return httpx.Response(200, json=geocode_payload(*([feature] if feature else [])))
        return directions_responses.pop(0)

    return handler


@pytest.fixture
def use_ors(monkeypatch):
    def install(handler, api_key=FAKE_API_KEY):
        monkeypatch.setattr(views, "build_ors_client", lambda: make_client(handler, api_key))

    return install


def post(payload):
    return APIClient().post(URL, payload, format="json")


def test_returns_three_routes_with_checkpoints(use_ors):
    calls = []
    use_ors(ors_handler([httpx.Response(200, json=directions_payload(*ALTERNATIVES))], calls=calls))

    response = post(VALID_REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["origin"] == {
        "query": "Waco, TX",
        "label": "Waco, TX, USA",
        "latitude": 30.0,
        "longitude": -97.0,
    }
    assert body["destination"]["label"] == "Temple, TX, USA"
    assert body["departure_time"] == "2026-10-19T08:00:00-05:00"
    assert body["checkpoint_interval_miles"] == 25
    assert body["load_weight_lbs"] == 42000.0
    assert body["requested_route_count"] == 3
    assert body["route_count"] == 3
    assert body["alternatives_note"] is None
    assert [r["id"] for r in body["routes"]] == ["route-1", "route-2", "route-3"]
    assert [r["provider_order"] for r in body["routes"]] == [0, 1, 2]
    assert [r["distance_miles"] for r in body["routes"]] == [70.0, 75.0, 80.0]
    assert [r["duration_seconds"] for r in body["routes"]] == [4200.0, 4000.0, 4500.0]

    first_route = body["routes"][0]
    assert first_route["geometry"][0] == [30.0, -97.0]
    assert first_route["geometry"][-1] == [31.0, -97.0]
    checkpoints = first_route["checkpoints"]
    assert [c["distance_miles"] for c in checkpoints] == [0.0, 25.0, 50.0, 70.0]
    assert [c["index"] for c in checkpoints] == [0, 1, 2, 3]
    assert checkpoints[0] == {
        "index": 0,
        "distance_miles": 0.0,
        "latitude": 30.0,
        "longitude": -97.0,
        "elapsed_seconds": 0.0,
        "eta": "2026-10-19T08:00:00-05:00",
    }
    assert checkpoints[-1]["latitude"] == 31.0
    assert checkpoints[-1]["elapsed_seconds"] == 4200.0
    assert checkpoints[-1]["eta"] == "2026-10-19T09:10:00-05:00"
    assert checkpoints[-1]["distance_miles"] == first_route["distance_miles"]

    directions_call = [c for c in calls if c.url.path.startswith("/v2/directions")]
    assert len(directions_call) == 1
    assert request_json(directions_call[0])["alternative_routes"]["target_count"] == 3


@pytest.mark.parametrize("route_count", [1, 2])
def test_fewer_routes_than_requested_are_not_padded(use_ors, route_count):
    payload = directions_payload(*ALTERNATIVES[:route_count])
    use_ors(ors_handler([httpx.Response(200, json=payload)]))

    body = post(VALID_REQUEST).json()

    assert body["route_count"] == route_count
    assert len(body["routes"]) == route_count
    assert body["requested_route_count"] == 3


LIMIT_ERROR = ors_error(400, 2004, "approximated route distance must not be greater than 100000.0 meters")
# Detour geometries bowing west and east of the meridian line, so neither overlaps it.
WEST_DETOUR = route_feature(
    80 * METERS_PER_MILE, 4_800, [[-97.0, 30.0], [-97.3, 30.5], [-97.0, 31.0]]
)
EAST_DETOUR = route_feature(
    85 * METERS_PER_MILE, 5_000, [[-97.0, 30.0], [-96.7, 30.5], [-97.0, 31.0]]
)


def directions_calls(calls):
    return [request_json(c) for c in calls if c.url.path.startswith("/v2/directions")]


def test_alternatives_limit_uses_via_point_detours(use_ors):
    calls = []
    use_ors(
        ors_handler(
            [
                LIMIT_ERROR,
                httpx.Response(200, json=directions_payload(ALTERNATIVES[0])),
                httpx.Response(200, json=directions_payload(WEST_DETOUR)),
                httpx.Response(200, json=directions_payload(EAST_DETOUR)),
            ],
            calls=calls,
        )
    )

    response = post(VALID_REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["route_count"] == 3
    assert [r["id"] for r in body["routes"]] == ["route-1", "route-2", "route-3"]
    assert [r["distance_miles"] for r in body["routes"]] == [70.0, 80.0, 85.0]
    assert "either side of the direct line" in body["alternatives_note"]
    requests = directions_calls(calls)
    assert len(requests) == 4
    assert "alternative_routes" in requests[0]
    assert "alternative_routes" not in requests[1]
    for detour in requests[2:]:
        assert len(detour["coordinates"]) == 3
        assert "alternative_routes" not in detour
        assert detour["radiuses"] == [350, -1, 350]
    # The two via points sit on opposite sides of the straight line (longitude -97).
    via_lngs = [detour["coordinates"][1][0] for detour in requests[2:]]
    assert via_lngs[0] < -97.0 < via_lngs[1] or via_lngs[1] < -97.0 < via_lngs[0]


def test_duplicate_and_overlong_detours_are_rejected(use_ors):
    overlong = route_feature(200 * METERS_PER_MILE, 9_000, [[-97.0, 30.0], [-98.0, 30.5], [-97.0, 31.0]])
    use_ors(
        ors_handler(
            [
                LIMIT_ERROR,
                httpx.Response(200, json=directions_payload(ALTERNATIVES[0])),
                # Same road as the best route: a duplicate, not an alternative.
                httpx.Response(200, json=directions_payload(ALTERNATIVES[1])),
                httpx.Response(200, json=directions_payload(overlong)),
                ors_error(404, 2009),
                httpx.Response(200, json=directions_payload(ALTERNATIVES[2])),
            ]
        )
    )

    body = post(VALID_REQUEST).json()

    assert body["route_count"] == 1
    assert "single best route" in body["alternatives_note"]


def test_partial_detour_result_names_route_count(use_ors):
    use_ors(
        ors_handler(
            [
                LIMIT_ERROR,
                httpx.Response(200, json=directions_payload(ALTERNATIVES[0])),
                httpx.Response(200, json=directions_payload(WEST_DETOUR)),
                httpx.Response(200, json=directions_payload(WEST_DETOUR)),
                httpx.Response(200, json=directions_payload(ALTERNATIVES[0])),
                ors_error(404, 2009),
            ]
        )
    )

    body = post(VALID_REQUEST).json()

    assert body["route_count"] == 2
    assert "Only 2 distinct routes were found." in body["alternatives_note"]


def test_quota_exhaustion_during_detours_keeps_found_routes(use_ors):
    calls = []
    use_ors(
        ors_handler(
            [
                LIMIT_ERROR,
                httpx.Response(200, json=directions_payload(ALTERNATIVES[0])),
                httpx.Response(200, json=directions_payload(WEST_DETOUR)),
                httpx.Response(403, json={"error": "Quota exceeded"}),
            ],
            calls=calls,
        )
    )

    response = post(VALID_REQUEST)

    assert response.status_code == 200
    assert response.json()["route_count"] == 2
    # The search stops at the quota error instead of trying the remaining offsets.
    assert len(directions_calls(calls)) == 4


def test_quota_exceeded_is_reported_as_such(use_ors):
    use_ors(ors_handler(geocode=lambda request: httpx.Response(403, json={"error": "Quota exceeded"})))

    response = post(VALID_REQUEST)

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "routing_quota_exceeded"
    assert "quota" in error["message"]


def test_route_over_provider_limit_even_without_alternatives(use_ors):
    use_ors(ors_handler([ors_error(400, 2004), ors_error(400, 2004)]))

    response = post(VALID_REQUEST)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "route_too_long"


@pytest.mark.parametrize("interval", [10, 25, 50, "10"])
def test_each_allowed_interval_is_accepted(use_ors, interval):
    use_ors(ors_handler([httpx.Response(200, json=directions_payload(ALTERNATIVES[0]))]))

    body = post({**VALID_REQUEST, "checkpoint_interval_miles": interval}).json()

    step = int(interval)
    expected = [float(d) for d in range(0, 70, step)] + [70.0]
    assert body["checkpoint_interval_miles"] == step
    assert [c["distance_miles"] for c in body["routes"][0]["checkpoints"]] == expected


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("origin", ""),
        ("origin", "   "),
        ("destination", None),
        ("departure_time", "2026-10-19T08:00:00"),
        ("departure_time", "2026-10-19"),
        ("departure_time", "tomorrow morning"),
        ("checkpoint_interval_miles", 15),
        ("checkpoint_interval_miles", 0),
        ("checkpoint_interval_miles", "fifty"),
        ("load_weight_lbs", 0),
        ("load_weight_lbs", -100),
        ("load_weight_lbs", "NaN"),
        ("load_weight_lbs", "Infinity"),
        ("load_weight_lbs", "-inf"),
        ("load_weight_lbs", True),
        ("load_weight_lbs", "heavy"),
    ],
)
def test_invalid_fields_return_400(use_ors, field, value):
    calls = []
    use_ors(ors_handler(calls=calls))

    response = post({**VALID_REQUEST, field: value})

    assert response.status_code == 400
    assert field in response.json()
    assert calls == []


@pytest.mark.parametrize("missing", list(VALID_REQUEST))
def test_missing_fields_return_400(use_ors, missing):
    use_ors(ors_handler())
    payload = {k: v for k, v in VALID_REQUEST.items() if k != missing}

    response = post(payload)

    assert response.status_code == 400
    assert missing in response.json()


def test_naive_departure_time_error_is_explicit(use_ors):
    use_ors(ors_handler())

    response = post({**VALID_REQUEST, "departure_time": "2026-10-19T08:00:00"})

    assert "timezone offset" in response.json()["departure_time"][0]


def test_utc_z_suffix_is_accepted_and_preserved(use_ors):
    use_ors(ors_handler([httpx.Response(200, json=directions_payload(ALTERNATIVES[0]))]))

    body = post({**VALID_REQUEST, "departure_time": "2026-10-19T13:00:00Z"}).json()

    assert body["departure_time"] == "2026-10-19T13:00:00+00:00"


def test_ambiguous_location_returns_422_with_candidates(use_ors):
    def geocode(request):
        return httpx.Response(
            200,
            json=geocode_payload(
                geocode_feature("Springfield, IL, USA", 39.78, -89.65),
                geocode_feature("Springfield, MO, USA", 37.21, -93.29),
            ),
        )

    use_ors(ors_handler(geocode=geocode))

    response = post({**VALID_REQUEST, "origin": "Springfield"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "ambiguous_location",
            "message": (
                '"Springfield" matches several places. Please be more specific. '
                "Search is limited to country code US (server setting ORS_GEOCODE_COUNTRY)."
            ),
            "query": "Springfield",
            "candidates": ["Springfield, IL, USA", "Springfield, MO, USA"],
        }
    }


def test_unknown_location_returns_422(use_ors):
    use_ors(ors_handler())

    response = post({**VALID_REQUEST, "destination": "Atlantis"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "location_not_found"
    assert response.json()["error"]["query"] == "Atlantis"


def test_same_origin_and_destination_returns_422(use_ors):
    use_ors(ors_handler())

    response = post({**VALID_REQUEST, "destination": "Waco, TX"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "same_location"


def test_missing_api_key_returns_503(use_ors):
    use_ors(ors_handler(), api_key="")

    response = post(VALID_REQUEST)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "routing_not_configured"


def test_timeout_returns_504(use_ors):
    def timeout(request):
        raise httpx.ReadTimeout("timed out")

    use_ors(ors_handler(geocode=timeout))

    response = post(VALID_REQUEST)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "routing_timeout"


@pytest.mark.parametrize(
    ("directions_response", "status", "code"),
    [
        (httpx.Response(500, text=f"internal {FAKE_API_KEY}"), 502, "routing_unavailable"),
        (httpx.Response(401, text=f"invalid key {FAKE_API_KEY}"), 502, "routing_auth_failed"),
        (ors_error(404, 2010, f"point not found {FAKE_API_KEY}"), 422, "route_not_found"),
        (httpx.Response(200, text=f"garbage {FAKE_API_KEY}"), 502, "invalid_route_data"),
        (
            httpx.Response(200, json=directions_payload(route_feature(1000, 60, [[-97.0, 30.0]]))),
            502,
            "invalid_route_data",
        ),
    ],
)
def test_provider_failures_are_sanitized(use_ors, caplog, directions_response, status, code):
    caplog.set_level(logging.DEBUG)
    use_ors(ors_handler([directions_response]))

    response = post(VALID_REQUEST)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert FAKE_API_KEY not in response.content.decode()
    assert FAKE_API_KEY not in caplog.text


def test_get_is_not_allowed():
    assert APIClient().get(URL).status_code == 405
