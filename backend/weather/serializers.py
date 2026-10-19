"""Request validation and response shaping for the weather forecast-window API."""

import math
from typing import Any

from rest_framework import serializers

from routes.serializers import (
    AwareDateTimeField,
    PositiveFiniteFloatField,
    serialize_risk,
    serialize_weather,
)
from weather.window import MAX_WINDOW_LOCATIONS, ForecastWindowResult

COORDINATE_DECIMALS = 6


class FiniteFloatField(serializers.FloatField):
    default_error_messages = {"not_finite": "Must be a finite number."}

    def to_internal_value(self, data):
        if isinstance(data, bool):
            self.fail("invalid")
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail("not_finite")
        return value


class LocationSerializer(serializers.Serializer):
    latitude = FiniteFloatField(min_value=-90, max_value=90)
    longitude = FiniteFloatField(min_value=-180, max_value=180)


class ForecastWindowRequestSerializer(serializers.Serializer):
    locations = serializers.ListField(
        child=LocationSerializer(), min_length=1, max_length=MAX_WINDOW_LOCATIONS
    )
    departure_time = AwareDateTimeField()
    load_weight_lbs = PositiveFiniteFloatField()


def serialize_forecast_window(result: ForecastWindowResult) -> dict[str, Any]:
    return {
        "departure_time": result.departure_time.isoformat(),
        "load_weight_lbs": result.load_weight_lbs,
        "step_hours": 1,
        "max_offset_hours": result.slots[-1].offset_hours,
        "slots": [
            {
                "offset_hours": slot.offset_hours,
                "target_time": slot.target_time.isoformat(),
                "forecast_time": slot.forecast_time.isoformat() if slot.forecast_time else None,
            }
            for slot in result.slots
        ],
        "locations": [
            {
                "latitude": round(location.latitude, COORDINATE_DECIMALS),
                "longitude": round(location.longitude, COORDINATE_DECIMALS),
                "observations": [
                    {"weather": serialize_weather(o.weather), "risk": serialize_risk(o.risk)}
                    for o in location.observations
                ],
            }
            for location in result.locations
        ],
        "coverage_note": result.coverage_note,
    }
