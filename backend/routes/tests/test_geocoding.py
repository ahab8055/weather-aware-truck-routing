import pytest

from routes.errors import AmbiguousLocation, LocationNotFound
from routes.geocoding import resolve_location
from routes.ors import GeocodeCandidate


class FakeGeocoder:
    def __init__(self, *candidates):
        self.candidates = tuple(GeocodeCandidate(*c) for c in candidates)
        self.queries = []

    def geocode(self, text, size=5):
        self.queries.append(text)
        return self.candidates


def test_single_confident_match_is_used():
    geocoder = FakeGeocoder(("Dallas, TX, USA", 32.7767, -96.797, 1.0))

    location = resolve_location(geocoder, "Dallas, TX")

    assert location.query == "Dallas, TX"
    assert location.label == "Dallas, TX, USA"
    assert location.coordinates == (32.7767, -96.797)


def test_clear_winner_over_weaker_matches_is_used():
    geocoder = FakeGeocoder(
        ("Houston, TX, USA", 29.7604, -95.3698, 1.0),
        ("Houston, MO, USA", 37.3262, -91.9558, 0.85),
        ("Houston, MS, USA", 33.8987, -89.0003, 0.6),
    )

    assert resolve_location(geocoder, "Houston").label == "Houston, TX, USA"


def test_zero_matches_raise_location_not_found():
    with pytest.raises(LocationNotFound) as excinfo:
        resolve_location(FakeGeocoder(), "Xyzzyville")

    assert "Xyzzyville" in excinfo.value.message
    assert excinfo.value.http_status == 422


def test_only_low_confidence_matches_raise_location_not_found_with_candidates():
    geocoder = FakeGeocoder(("Somewhere Rd, Austin, TX, USA", 30.2, -97.7, 0.5))

    with pytest.raises(LocationNotFound) as excinfo:
        resolve_location(geocoder, "somewhere")

    assert excinfo.value.details["candidates"] == ["Somewhere Rd, Austin, TX, USA"]


def test_equally_confident_matches_are_ambiguous():
    geocoder = FakeGeocoder(
        ("Springfield, IL, USA", 39.7817, -89.6501, 1.0),
        ("Springfield, MO, USA", 37.2090, -93.2923, 1.0),
        ("Springfield, MA, USA", 42.1015, -72.5898, 0.95),
    )

    with pytest.raises(AmbiguousLocation) as excinfo:
        resolve_location(geocoder, "Springfield")

    assert excinfo.value.code == "ambiguous_location"
    assert excinfo.value.details["candidates"] == [
        "Springfield, IL, USA",
        "Springfield, MO, USA",
        "Springfield, MA, USA",
    ]


def test_duplicate_labels_do_not_count_as_ambiguity():
    geocoder = FakeGeocoder(
        ("Dallas, TX, USA", 32.7767, -96.797, 1.0),
        ("Dallas, TX, USA", 32.7790, -96.800, 1.0),
    )

    assert resolve_location(geocoder, "Dallas, TX").coordinates == (32.7767, -96.797)


class RegionalGeocoder(FakeGeocoder):
    geocode_country = "US"


def test_not_found_message_names_the_active_country_filter():
    with pytest.raises(LocationNotFound) as excinfo:
        resolve_location(RegionalGeocoder(), "Lahore, Pakistan")

    assert excinfo.value.message == (
        'No location found for "Lahore, Pakistan". Search is limited to country code US '
        "(server setting ORS_GEOCODE_COUNTRY)."
    )


def test_ambiguous_message_names_the_active_country_filter():
    geocoder = RegionalGeocoder(
        ("Springfield, IL, USA", 39.78, -89.65, 1.0),
        ("Springfield, MO, USA", 37.21, -93.29, 1.0),
    )

    with pytest.raises(AmbiguousLocation) as excinfo:
        resolve_location(geocoder, "Springfield")

    assert "limited to country code US" in excinfo.value.message


def test_no_region_hint_when_geocoding_is_worldwide():
    with pytest.raises(LocationNotFound) as excinfo:
        resolve_location(FakeGeocoder(), "Nowhere")

    assert "limited to" not in excinfo.value.message


def test_tie_is_broken_by_a_single_exact_label_match():
    # Regression: live ORS returned these equally confident matches for "Islamabad, Pakistan",
    # so picking the "Islamabad, Pakistan" suggestion in the UI could never resolve.
    geocoder = FakeGeocoder(
        ("Anantnag, Pakistan", 33.73, 75.15, 1.0),
        ("Islamabad, Pakistan", 33.6938, 73.0652, 1.0),
        ("Islamabad, SD, Pakistan", 25.0, 68.0, 1.0),
    )

    location = resolve_location(geocoder, "  islamabad,pakistan ")

    assert location.label == "Islamabad, Pakistan"
    assert location.coordinates == (33.6938, 73.0652)


def test_low_confidence_exact_label_is_ignored():
    geocoder = FakeGeocoder(
        ("Springfield, IL, USA", 39.78, -89.65, 1.0),
        ("Springfield", 37.21, -93.29, 0.5),
    )

    # The exact-label candidate is below MIN_CONFIDENCE; the single confident match wins.
    assert resolve_location(geocoder, "Springfield").label == "Springfield, IL, USA"


def test_tie_without_exact_match_stays_ambiguous():
    geocoder = FakeGeocoder(
        ("Islamabad, Pakistan", 33.69, 73.07, 1.0),
        ("Islamabad, SD, Pakistan", 25.0, 68.0, 1.0),
    )

    with pytest.raises(AmbiguousLocation):
        resolve_location(geocoder, "Islamabad")


def test_low_confidence_exact_label_breaks_a_tie():
    # Regression: live ORS search scored the picked "Peshawar Division, KP, Pakistan"
    # suggestion at 0.6 while two other matches tied at 0.8, so the pick was reported ambiguous.
    geocoder = FakeGeocoder(
        ("Peshawar Division, KP, Pakistan", 34.00081, 71.78231, 0.6),
        ("Peshawar, KP, Pakistan", 34.088306, 71.513381, 0.8),
        ("Islamia College University peshawar, KP, Pakistan", 33.999817, 71.47598, 0.8),
    )

    location = resolve_location(geocoder, "Peshawar Division, KP, Pakistan")

    assert location.label == "Peshawar Division, KP, Pakistan"
    assert location.coordinates == (34.00081, 71.78231)


def test_low_confidence_exact_label_is_used_when_nothing_is_confident():
    geocoder = FakeGeocoder(
        ("Peshawar Division, KP, Pakistan", 34.0, 71.78, 0.6),
        ("Peshawar, KP, Pakistan", 34.0, 71.56, 0.5),
    )

    assert resolve_location(geocoder, "Peshawar Division, KP, Pakistan").label == "Peshawar Division, KP, Pakistan"

