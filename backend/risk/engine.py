"""Weather classification and per-checkpoint risk assessment.

Units: wind in mph, rain and snow intensity in inches per hour, load in pounds.
"""

import math
from dataclasses import dataclass
from enum import StrEnum

from risk.levels import RiskLevel


@dataclass(frozen=True)
class Threshold:
    """A level applies while the value is below `upper` (or equal, if inclusive)."""

    level: RiskLevel
    upper: float
    upper_inclusive: bool = False

    def contains(self, value: float) -> bool:
        return value <= self.upper if self.upper_inclusive else value < self.upper


# Values beyond the last threshold in each table are NO_TRAVEL.
WIND_MPH_THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(RiskLevel.LOW, 25),
    Threshold(RiskLevel.MODERATE, 35),
    Threshold(RiskLevel.HIGH, 45),
    Threshold(RiskLevel.SEVERE, 55),
)

RAIN_IN_PER_HR_THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(RiskLevel.LOW, 0.10),
    Threshold(RiskLevel.MODERATE, 0.25),
    Threshold(RiskLevel.HIGH, 0.50),
    Threshold(RiskLevel.SEVERE, 1.00, upper_inclusive=True),
)

SNOW_IN_PER_HR_THRESHOLDS: tuple[Threshold, ...] = (
    Threshold(RiskLevel.LOW, 0.5),
    Threshold(RiskLevel.MODERATE, 1.0),
    Threshold(RiskLevel.HIGH, 2.0),
    Threshold(RiskLevel.SEVERE, 3.0, upper_inclusive=True),
)

# Load-specific wind restrictions. Wind >= 55 mph is No Travel for every load
# and is already covered by WIND_MPH_THRESHOLDS.
HEAVY_LOAD_NO_TRAVEL_WIND_MPH = 45
HEAVY_LOAD_NO_TRAVEL_LB = 30_000
HEAVY_LOAD_SEVERE_WIND_MPH = 35
HEAVY_LOAD_SEVERE_LB = 40_000


def validate_measurement(value: float, name: str) -> float:
    """Return `value` as a float if it is a finite, non-negative number; raise otherwise."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value}")
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return float(value)


def _classify(value: float, thresholds: tuple[Threshold, ...], name: str) -> RiskLevel:
    value = validate_measurement(value, name)
    for threshold in thresholds:
        if threshold.contains(value):
            return threshold.level
    return RiskLevel.NO_TRAVEL


def classify_wind(wind_speed_mph: float) -> RiskLevel:
    """Classify wind speed in mph."""
    return _classify(wind_speed_mph, WIND_MPH_THRESHOLDS, "wind_speed_mph")


def classify_rain(rain_in_per_hr: float) -> RiskLevel:
    """Classify rain intensity in inches per hour."""
    return _classify(rain_in_per_hr, RAIN_IN_PER_HR_THRESHOLDS, "rain_in_per_hr")


def classify_snow(snow_in_per_hr: float) -> RiskLevel:
    """Classify snow intensity in inches per hour."""
    return _classify(snow_in_per_hr, SNOW_IN_PER_HR_THRESHOLDS, "snow_in_per_hr")


@dataclass(frozen=True)
class WeatherConditions:
    """Forecast conditions at one checkpoint. Validated on construction."""

    wind_speed_mph: float
    rain_in_per_hr: float
    snow_in_per_hr: float

    def __post_init__(self) -> None:
        for name in ("wind_speed_mph", "rain_in_per_hr", "snow_in_per_hr"):
            object.__setattr__(self, name, validate_measurement(getattr(self, name), name))


class LoadRestriction(StrEnum):
    """Which load-specific rule, if any, raised the checkpoint above its weather risk."""

    NONE = "none"
    HEAVY_LOAD_WIND_SEVERE = "heavy_load_wind_severe"
    HEAVY_LOAD_WIND_NO_TRAVEL = "heavy_load_wind_no_travel"


@dataclass(frozen=True)
class CheckpointRisk:
    """Risk at one checkpoint, keeping each weather factor's own classification."""

    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    base: RiskLevel
    overall: RiskLevel
    load_restriction: LoadRestriction


def assess_checkpoint(conditions: WeatherConditions, load_weight_lb: float) -> CheckpointRisk:
    """Classify each weather factor, take the worst, then apply load-specific wind rules."""
    load_weight_lb = validate_measurement(load_weight_lb, "load_weight_lb")
    wind = classify_wind(conditions.wind_speed_mph)
    rain = classify_rain(conditions.rain_in_per_hr)
    snow = classify_snow(conditions.snow_in_per_hr)
    base = max(wind, rain, snow)

    overall = base
    restriction = LoadRestriction.NONE
    wind_mph = conditions.wind_speed_mph
    if wind_mph >= HEAVY_LOAD_NO_TRAVEL_WIND_MPH and load_weight_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        if base < RiskLevel.NO_TRAVEL:
            overall = RiskLevel.NO_TRAVEL
            restriction = LoadRestriction.HEAVY_LOAD_WIND_NO_TRAVEL
    elif wind_mph >= HEAVY_LOAD_SEVERE_WIND_MPH and load_weight_lb > HEAVY_LOAD_SEVERE_LB:
        if base < RiskLevel.SEVERE:
            overall = RiskLevel.SEVERE
            restriction = LoadRestriction.HEAVY_LOAD_WIND_SEVERE

    return CheckpointRisk(
        wind=wind,
        rain=rain,
        snow=snow,
        base=base,
        overall=overall,
        load_restriction=restriction,
    )
