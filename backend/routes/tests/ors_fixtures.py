"""Builders for fake OpenRouteService payloads and stubbed clients (no network)."""

import json
from collections.abc import Callable, Sequence

import httpx

from routes.ors import ORSClient

# Fake key; tests assert it never leaks into errors, responses or logs.
FAKE_API_KEY = "fake-ors-key-7d1e9b42c0"
BASE_URL = "https://ors.test"
METERS_PER_MILE = 1609.344

# A north-south line along longitude -97 from 30.0 N to 31.0 N (~69.09 miles),
# with deliberately unequal vertex spacing. Stored as ORS [lng, lat].
MERIDIAN_LNGLAT = [[-97.0, 30.0], [-97.0, 30.1], [-97.0, 30.7], [-97.0, 31.0]]
MERIDIAN_MILES = 69.0934


def geocode_feature(label: str, lat: float, lng: float, confidence: float = 1.0) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": {"label": label, "confidence": confidence},
    }


def geocode_payload(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def route_feature(
    distance_meters: float, duration_seconds: float, lnglat: Sequence[Sequence[float]]
) -> dict:
    return {
        "type": "Feature",
        "properties": {"summary": {"distance": distance_meters, "duration": duration_seconds}},
        "geometry": {"type": "LineString", "coordinates": [list(c) for c in lnglat]},
    }


def directions_payload(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def ors_error(status: int, code: int, message: str = "error") -> httpx.Response:
    return httpx.Response(status, json={"error": {"code": code, "message": message}})


def make_client(
    handler: Callable[[httpx.Request], httpx.Response], api_key: str = FAKE_API_KEY
) -> ORSClient:
    return ORSClient(
        api_key=api_key,
        base_url=BASE_URL,
        geocode_country="US",
        transport=httpx.MockTransport(handler),
    )


def request_json(request: httpx.Request) -> dict:
    return json.loads(request.content)
