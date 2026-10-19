import math

import pytest

from risk.engine import (
    LoadRestriction,
    WeatherConditions,
    assess_checkpoint,
    classify_rain,
    classify_snow,
    classify_wind,
)
from risk.levels import RiskLevel, risk_score

LOW, MODERATE, HIGH, SEVERE, NO_TRAVEL = RiskLevel

CLASSIFIERS = [classify_wind, classify_rain, classify_snow]


@pytest.mark.parametrize(
    ("wind_mph", "expected"),
    [
        (0, LOW),
        (24.99, LOW),
        (25, MODERATE),
        (25.01, MODERATE),
        (34.99, MODERATE),
        (35, HIGH),
        (35.01, HIGH),
        (44.99, HIGH),
        (45, SEVERE),
        (45.01, SEVERE),
        (54.99, SEVERE),
        (55, NO_TRAVEL),
        (55.01, NO_TRAVEL),
        (120, NO_TRAVEL),
    ],
)
def test_classify_wind(wind_mph, expected):
    assert classify_wind(wind_mph) is expected


@pytest.mark.parametrize(
    ("rain_in_per_hr", "expected"),
    [
        (0, LOW),
        (0.09, LOW),
        (0.10, MODERATE),
        (0.11, MODERATE),
        (0.24, MODERATE),
        (0.25, HIGH),
        (0.26, HIGH),
        (0.49, HIGH),
        (0.50, SEVERE),
        (0.51, SEVERE),
        (0.99, SEVERE),
        (1.00, SEVERE),
        (1.01, NO_TRAVEL),
    ],
)
def test_classify_rain(rain_in_per_hr, expected):
    assert classify_rain(rain_in_per_hr) is expected


@pytest.mark.parametrize(
    ("snow_in_per_hr", "expected"),
    [
        (0, LOW),
        (0.49, LOW),
        (0.5, MODERATE),
        (0.51, MODERATE),
        (0.99, MODERATE),
        (1.0, HIGH),
        (1.01, HIGH),
        (1.99, HIGH),
        (2.0, SEVERE),
        (2.01, SEVERE),
        (2.99, SEVERE),
        (3.0, SEVERE),
        (3.01, NO_TRAVEL),
    ],
)
def test_classify_snow(snow_in_per_hr, expected):
    assert classify_snow(snow_in_per_hr) is expected


@pytest.mark.parametrize("classify", CLASSIFIERS)
@pytest.mark.parametrize("value", [-0.01, -1, -math.inf])
def test_classifiers_reject_negative_values(classify, value):
    with pytest.raises(ValueError):
        classify(value)


@pytest.mark.parametrize("classify", CLASSIFIERS)
@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_classifiers_reject_non_finite_values(classify, value):
    with pytest.raises(ValueError, match="finite"):
        classify(value)


@pytest.mark.parametrize("classify", CLASSIFIERS)
@pytest.mark.parametrize("value", [None, "10", True])
def test_classifiers_reject_non_numbers(classify, value):
    with pytest.raises(TypeError):
        classify(value)


@pytest.mark.parametrize(
    "fields",
    [
        {"wind_speed_mph": math.nan, "rain_in_per_hr": 0, "snow_in_per_hr": 0},
        {"wind_speed_mph": 0, "rain_in_per_hr": -0.1, "snow_in_per_hr": 0},
        {"wind_speed_mph": 0, "rain_in_per_hr": 0, "snow_in_per_hr": math.inf},
    ],
)
def test_weather_conditions_validate_on_construction(fields):
    with pytest.raises(ValueError):
        WeatherConditions(**fields)


def weather(wind=0.0, rain=0.0, snow=0.0):
    return WeatherConditions(wind_speed_mph=wind, rain_in_per_hr=rain, snow_in_per_hr=snow)


@pytest.mark.parametrize(
    ("wind_mph", "load_lb", "expected_overall", "expected_restriction"),
    [
        # Wind >= 55 mph is No Travel for every load, straight from the wind table.
        (55, 0, NO_TRAVEL, LoadRestriction.NONE),
        (55, 80_000, NO_TRAVEL, LoadRestriction.NONE),
        # The 45 mph rule needs load strictly greater than 30,000 lb.
        (45, 30_000, SEVERE, LoadRestriction.NONE),
        (45, 30_001, NO_TRAVEL, LoadRestriction.HEAVY_LOAD_WIND_NO_TRAVEL),
        (44.99, 45_000, SEVERE, LoadRestriction.HEAVY_LOAD_WIND_SEVERE),
        # The 35 mph rule needs load strictly greater than 40,000 lb.
        (35, 40_000, HIGH, LoadRestriction.NONE),
        (35, 40_001, SEVERE, LoadRestriction.HEAVY_LOAD_WIND_SEVERE),
        (34.99, 80_000, MODERATE, LoadRestriction.NONE),
        (20, 80_000, LOW, LoadRestriction.NONE),
    ],
)
def test_load_specific_wind_restrictions(wind_mph, load_lb, expected_overall, expected_restriction):
    risk = assess_checkpoint(weather(wind=wind_mph), load_lb)

    assert risk.overall is expected_overall
    assert risk.load_restriction is expected_restriction


def test_rain_dominates_low_wind_and_factors_are_preserved():
    risk = assess_checkpoint(weather(wind=10, rain=0.6, snow=0.2), 20_000)

    assert (risk.wind, risk.rain, risk.snow) == (LOW, SEVERE, LOW)
    assert risk.base is SEVERE
    assert risk.overall is SEVERE
    assert risk.load_restriction is LoadRestriction.NONE


def test_snow_no_travel_beats_heavy_load_severe_rule():
    risk = assess_checkpoint(weather(wind=36, snow=3.5), 40_001)

    assert (risk.wind, risk.snow) == (HIGH, NO_TRAVEL)
    assert risk.overall is NO_TRAVEL
    assert risk.load_restriction is LoadRestriction.NONE


def test_heavy_load_severe_rule_not_labelled_when_rain_already_severe():
    risk = assess_checkpoint(weather(wind=40, rain=0.75), 42_000)

    assert risk.overall is SEVERE
    assert risk.load_restriction is LoadRestriction.NONE


def test_heavy_load_no_travel_rule_raises_severe_rain():
    risk = assess_checkpoint(weather(wind=46, rain=0.75), 35_000)

    assert risk.base is SEVERE
    assert risk.overall is NO_TRAVEL
    assert risk.load_restriction is LoadRestriction.HEAVY_LOAD_WIND_NO_TRAVEL


@pytest.mark.parametrize("load_lb", [-1, math.nan, math.inf, -math.inf])
def test_assess_checkpoint_rejects_invalid_load(load_lb):
    with pytest.raises(ValueError):
        assess_checkpoint(weather(), load_lb)


def test_risk_scores_exclude_no_travel():
    assert [risk_score(level) for level in (LOW, MODERATE, HIGH, SEVERE)] == [0, 1, 2, 3]
    with pytest.raises(ValueError):
        risk_score(NO_TRAVEL)
