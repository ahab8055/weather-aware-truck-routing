import logging

import httpx
import pytest

from routes.errors import (
    ProviderLimitExceeded,
    LocationNotRoutable,
    RouteNotFound,
    RoutingDataError,
    RoutingError,
    RoutingNotConfigured,
    RoutingTimeout,
    RoutingUnavailable,
)
from routes.ors import ORSClient
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

START = (30.0, -97.0)
END = (31.0, -97.0)


def test_geocode_parses_candidates_and_swaps_to_lat_lng():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(
            200,
            json=geocode_payload(
                geocode_feature("Dallas, TX, USA", 32.7767, -96.797, 1.0),
                geocode_feature("Dallas, GA, USA", 33.9237, -84.8408, 0.6),
            ),
        )

    candidates = make_client(handler).geocode("Dallas")

    assert [(c.label, c.latitude, c.longitude, c.confidence) for c in candidates] == [
        ("Dallas, TX, USA", 32.7767, -96.797, 1.0),
        ("Dallas, GA, USA", 33.9237, -84.8408, 0.6),
    ]
    request = seen["request"]
    assert request.url.path == "/geocode/search"
    assert request.url.params["text"] == "Dallas"
    assert request.url.params["boundary.country"] == "US"
    assert request.headers["Authorization"] == FAKE_API_KEY
    assert FAKE_API_KEY not in str(request.url)


def test_geocode_with_no_features_returns_empty():
    client = make_client(lambda request: httpx.Response(200, json=geocode_payload()))

    assert client.geocode("Nowhere") == ()


@pytest.mark.parametrize("route_count", [1, 2, 3])
def test_directions_returns_each_provider_route_in_order(route_count):
    features = [
        route_feature(100_000 + 10_000 * i, 4_000 + 100 * i, MERIDIAN_LNGLAT)
        for i in range(route_count)
    ]
    client = make_client(lambda request: httpx.Response(200, json=directions_payload(*features)))

    routes = client.directions(START, END, alternatives=3)

    assert len(routes) == route_count
    assert [r.provider_order for r in routes] == list(range(route_count))
    assert [r.distance_miles for r in routes] == pytest.approx(
        [(100_000 + 10_000 * i) / METERS_PER_MILE for i in range(route_count)]
    )
    assert [r.duration_seconds for r in routes] == [4_000 + 100 * i for i in range(route_count)]


def test_directions_normalizes_units_and_coordinate_order():
    feature = route_feature(160_934.4, 7_200, MERIDIAN_LNGLAT)
    client = make_client(lambda request: httpx.Response(200, json=directions_payload(feature)))

    (route,) = client.directions(START, END)

    assert route.distance_miles == pytest.approx(100.0)
    assert route.duration_seconds == 7_200
    assert route.geometry == ((30.0, -97.0), (30.1, -97.0), (30.7, -97.0), (31.0, -97.0))


def test_directions_request_shape():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(
            200, json=directions_payload(route_feature(1000, 60, MERIDIAN_LNGLAT))
        )

    make_client(handler).directions(START, END, alternatives=3)

    request = seen["request"]
    body = request_json(request)
    assert request.method == "POST"
    assert request.url.path == "/v2/directions/driving-hgv/geojson"
    assert body["coordinates"] == [[-97.0, 30.0], [-97.0, 31.0]]
    assert body["alternative_routes"]["target_count"] == 3
    assert body["units"] == "m"
    assert request.headers["Authorization"] == FAKE_API_KEY
    assert FAKE_API_KEY not in str(request.url)


def test_single_route_request_omits_alternatives():
    seen = {}

    def handler(request):
        seen["body"] = request_json(request)
        return httpx.Response(
            200, json=directions_payload(route_feature(1000, 60, MERIDIAN_LNGLAT))
        )

    make_client(handler).directions(START, END, alternatives=1)

    assert "alternative_routes" not in seen["body"]


def test_missing_api_key_fails_before_any_http_call():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=geocode_payload())

    client = make_client(handler, api_key="")

    with pytest.raises(RoutingNotConfigured):
        client.geocode("Dallas")
    with pytest.raises(RoutingNotConfigured):
        client.directions(START, END)
    assert calls == []


def raise_(exception):
    def handler(request):
        raise exception

    return handler


@pytest.mark.parametrize(
    ("handler", "expected_error", "expected_code"),
    [
        (raise_(httpx.ReadTimeout("timed out")), RoutingTimeout, "routing_timeout"),
        (raise_(httpx.ConnectTimeout("timed out")), RoutingTimeout, "routing_timeout"),
        (raise_(httpx.ConnectError("refused")), RoutingUnavailable, "routing_unavailable"),
        (lambda r: httpx.Response(500, text="boom"), RoutingUnavailable, "routing_unavailable"),
        (lambda r: httpx.Response(503), RoutingUnavailable, "routing_unavailable"),
        (lambda r: ors_error(401, 1), RoutingUnavailable, "routing_auth_failed"),
        (lambda r: httpx.Response(403, text="Access to this API has been disallowed"), RoutingUnavailable, "routing_auth_failed"),
        (lambda r: httpx.Response(429), RoutingUnavailable, "routing_rate_limited"),
        (lambda r: httpx.Response(403, json={"error": "Quota exceeded"}), RoutingUnavailable, "routing_quota_exceeded"),
        (lambda r: httpx.Response(429, json={"error": "Quota exceeded"}), RoutingUnavailable, "routing_quota_exceeded"),
        (lambda r: ors_error(404, 2010), RouteNotFound, "route_not_found"),
        (
            lambda r: ors_error(404, 2010, "Could not find routable point within a radius of 350.0 meters of specified coordinate 1: -118.19 34.34."),
            LocationNotRoutable,
            "location_not_routable",
        ),
        (lambda r: ors_error(404, 2009), RouteNotFound, "route_not_found"),
        (lambda r: ors_error(400, 2003), RoutingUnavailable, "routing_unavailable"),
        (lambda r: ors_error(400, 2004), ProviderLimitExceeded, "provider_limit_exceeded"),
        (lambda r: httpx.Response(200, text="<html>not json"), RoutingDataError, "invalid_route_data"),
        (lambda r: httpx.Response(200, json={"unexpected": True}), RoutingDataError, "invalid_route_data"),
        (lambda r: httpx.Response(200, json=directions_payload()), RoutingDataError, "invalid_route_data"),
    ],
)
def test_directions_error_mapping(handler, expected_error, expected_code):
    with pytest.raises(expected_error) as excinfo:
        make_client(handler).directions(START, END)

    assert excinfo.value.code == expected_code


@pytest.mark.parametrize(
    "lnglat",
    [
        [],
        [[-97.0, 30.0]],
        [[-97.0, 30.0], [-97.0, 30.0]],
        [[-97.0, 30.0], ["x", 31.0]],
        [[-97.0, 30.0], [-97.0]],
        [[-97.0, 30.0], [-97.0, 95.0]],
    ],
)
def test_directions_rejects_malformed_geometry(lnglat):
    feature = route_feature(1000, 60, lnglat)
    client = make_client(lambda request: httpx.Response(200, json=directions_payload(feature)))

    with pytest.raises(RoutingDataError):
        client.directions(START, END)


@pytest.mark.parametrize(("distance", "duration"), [(0, 60), (1000, 0), (-5, 60), (None, 60)])
def test_directions_rejects_invalid_summary(distance, duration):
    feature = route_feature(distance, duration, MERIDIAN_LNGLAT)
    client = make_client(lambda request: httpx.Response(200, json=directions_payload(feature)))

    with pytest.raises(RoutingDataError):
        client.directions(START, END)


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(200, json={"features": [{"geometry": {}}]}),
        lambda r: httpx.Response(200, text="nope"),
        lambda r: httpx.Response(400, json={"geocoding": {"errors": ["bad"]}}),
    ],
)
def test_geocode_errors_are_sanitized(handler):
    with pytest.raises(RoutingError):
        make_client(handler).geocode("Dallas")


@pytest.mark.parametrize(
    "handler",
    [
        raise_(httpx.ReadTimeout("timed out")),
        raise_(httpx.ConnectError("refused")),
        lambda r: httpx.Response(401, text=f"bad key {FAKE_API_KEY}"),
        lambda r: httpx.Response(500, text=f"echo {FAKE_API_KEY}"),
        lambda r: ors_error(400, 2004, f"echo {FAKE_API_KEY}"),
        lambda r: httpx.Response(200, text=f"not json {FAKE_API_KEY}"),
    ],
)
def test_api_key_never_appears_in_errors_or_logs(handler, caplog):
    caplog.set_level(logging.DEBUG)
    client = make_client(handler)

    for call in (lambda: client.geocode("Dallas"), lambda: client.directions(START, END)):
        with pytest.raises(RoutingError) as excinfo:
            call()
        error = excinfo.value
        assert FAKE_API_KEY not in str(error)
        assert FAKE_API_KEY not in repr(error)
        assert FAKE_API_KEY not in error.message
        # No chained httpx exception (which could carry request details) in tracebacks.
        assert error.__cause__ is None
        assert error.__context__ is None or error.__suppress_context__

    assert FAKE_API_KEY not in caplog.text
    assert FAKE_API_KEY not in repr(client)


def test_from_settings_reads_backend_settings(settings):
    settings.ORS_API_KEY = FAKE_API_KEY
    settings.ORS_BASE_URL = "https://ors.example"
    settings.ORS_GEOCODE_COUNTRY = ""

    client = ORSClient.from_settings()

    assert repr(client) == "ORSClient(base_url='https://ors.example')"
    client.close()


def strict_accept_handler(request):
    """Mirror live ORS: /geojson directions require an Accept that allows GeoJSON."""
    if request.url.path.endswith("/geojson") and "application/geo+json" not in request.headers.get("Accept", ""):
        return ors_error(406, 2007, "Unsupported export format")
    if request.url.path == "/geocode/search":
        return httpx.Response(200, json=geocode_payload(geocode_feature("Waco, TX, USA", 31.55, -97.15)))
    return httpx.Response(200, json=directions_payload(route_feature(1000, 60, MERIDIAN_LNGLAT)))


def test_directions_request_accepts_geojson():
    # Regression: live ORS returned 406/2007 when Accept was only application/json.
    routes = make_client(strict_accept_handler).directions(START, END)

    assert len(routes) == 1


def test_accept_headers_per_endpoint():
    seen = {}

    def handler(request):
        seen[request.url.path] = request.headers["Accept"]
        return strict_accept_handler(request)

    client = make_client(handler)
    client.geocode("Waco, TX")
    client.directions(START, END)

    assert seen["/geocode/search"] == "application/json"
    assert seen["/v2/directions/driving-hgv/geojson"] == "application/geo+json, application/json"


def test_autocomplete_request_and_parsing():
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(
            200,
            json=geocode_payload(
                geocode_feature("Houston, TX, USA", 29.78, -95.36),
                geocode_feature("Houston, MN, USA", 43.76, -91.57),
                geocode_feature("Houston County, GA, USA", 32.42, -83.67),
            ),
        )

    suggestions = make_client(handler).autocomplete("Hous", limit=2)

    assert [(s.label, s.latitude, s.longitude) for s in suggestions] == [
        ("Houston, TX, USA", 29.78, -95.36),
        ("Houston, MN, USA", 43.76, -91.57),
    ]
    request = seen["request"]
    assert request.url.path == "/geocode/autocomplete"
    assert request.url.params["text"] == "Hous"
    assert request.url.params["boundary.country"] == "US"
    assert request.headers["Authorization"] == FAKE_API_KEY
    assert request.headers["Accept"] == "application/json"
    assert FAKE_API_KEY not in str(request.url)


def test_autocomplete_missing_key_makes_no_request():
    calls = []
    client = make_client(lambda request: calls.append(request) or httpx.Response(200), api_key="")

    with pytest.raises(RoutingNotConfigured):
        client.autocomplete("Hous")
    assert calls == []


def test_directions_via_point_requests_single_route_through_it():
    seen = {}

    def handler(request):
        seen["body"] = request_json(request)
        feature = route_feature(80 * METERS_PER_MILE, 5_000, MERIDIAN_LNGLAT)
        return httpx.Response(200, json=directions_payload(feature))

    routes = make_client(handler).directions(START, END, alternatives=3, via=(30.5, -97.3))

    assert len(routes) == 1
    assert seen["body"]["coordinates"] == [[-97.0, 30.0], [-97.3, 30.5], [-97.0, 31.0]]
    assert seen["body"]["radiuses"] == [350, -1, 350]
    assert "alternative_routes" not in seen["body"]


def test_geocode_results_are_cached():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=geocode_payload(geocode_feature("Waco, TX, USA", 31.5, -97.1)))

    client = make_client(handler)
    first = client.geocode("Waco, TX")
    second = client.geocode("Waco, TX")
    client.geocode("Temple, TX")

    assert first == second
    assert len(calls) == 2


def test_geocode_errors_are_not_cached():
    responses = [
        httpx.Response(503),
        httpx.Response(200, json=geocode_payload(geocode_feature("Waco, TX, USA", 31.5, -97.1))),
    ]
    client = make_client(lambda request: responses.pop(0))

    with pytest.raises(RoutingUnavailable):
        client.geocode("Waco, TX")
    assert client.geocode("Waco, TX")[0].label == "Waco, TX, USA"
