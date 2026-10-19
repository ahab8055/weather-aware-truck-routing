"""Resolve free-text locations to a single place, refusing to guess when ambiguous."""

from dataclasses import dataclass
from typing import Protocol

from routes.errors import AmbiguousLocation, LocationNotFound
from routes.geometry import LatLng
from routes.ors import GeocodeCandidate

# Pelias confidence (0..1) a match needs to be used at all.
MIN_CONFIDENCE = 0.8
# How far the best match must lead the runner-up to be chosen automatically.
AMBIGUITY_MARGIN = 0.1
MAX_CANDIDATES_REPORTED = 5


class Geocoder(Protocol):
    def geocode(self, text: str, size: int = 5) -> tuple[GeocodeCandidate, ...]: ...


@dataclass(frozen=True)
class ResolvedLocation:
    """The user's query and the place it resolved to."""

    query: str
    label: str
    latitude: float
    longitude: float

    @property
    def coordinates(self) -> LatLng:
        return (self.latitude, self.longitude)


def _unique_by_label(candidates: tuple[GeocodeCandidate, ...]) -> list[GeocodeCandidate]:
    seen: set[str] = set()
    unique = []
    for candidate in sorted(candidates, key=lambda c: -c.confidence):
        if candidate.label not in seen:
            seen.add(candidate.label)
            unique.append(candidate)
    return unique


def _normalized(text: str) -> str:
    return " ".join(text.replace(",", ", ").split()).casefold()


def _region_hint(geocoder: Geocoder) -> str:
    country = getattr(geocoder, "geocode_country", "")
    if not country:
        return ""
    return f" Search is limited to country code {country} (server setting ORS_GEOCODE_COUNTRY)."


def _resolved(query: str, candidate: GeocodeCandidate) -> ResolvedLocation:
    return ResolvedLocation(
        query=query, label=candidate.label, latitude=candidate.latitude, longitude=candidate.longitude
    )


def _exact_label_match(candidates: list[GeocodeCandidate], query: str) -> GeocodeCandidate | None:
    exact = [c for c in candidates if _normalized(c.label) == _normalized(query)]
    return exact[0] if len(exact) == 1 else None


def resolve_location(geocoder: Geocoder, query: str) -> ResolvedLocation:
    """Geocode `query` and return the single confident match.

    Raises LocationNotFound when nothing (or nothing confident) matches, and
    AmbiguousLocation, listing the candidates, when several matches are
    equally plausible. Before giving up, a single candidate whose label is
    exactly the query text (e.g. a suggestion the user picked) is used, whatever
    its confidence: the search endpoint can score an autocomplete pick below
    MIN_CONFIDENCE. It never overrides a clear confident winner, and never guesses.
    """
    candidates = _unique_by_label(geocoder.geocode(query))
    hint = _region_hint(geocoder)
    if not candidates:
        raise LocationNotFound(f'No location found for "{query}".{hint}', details={"query": query})

    exact = _exact_label_match(candidates, query)
    confident = [c for c in candidates if c.confidence >= MIN_CONFIDENCE]
    if not confident:
        if exact:
            return _resolved(query, exact)
        raise LocationNotFound(
            f'No confident match for "{query}". Try a more specific address, "City, State" or "City, Country".{hint}',
            details={"query": query, "candidates": [c.label for c in candidates[:MAX_CANDIDATES_REPORTED]]},
        )

    best = confident[0]
    if len(confident) > 1 and best.confidence - confident[1].confidence < AMBIGUITY_MARGIN:
        if exact:
            return _resolved(query, exact)
        raise AmbiguousLocation(
            f'"{query}" matches several places. Please be more specific.{hint}',
            details={"query": query, "candidates": [c.label for c in confident[:MAX_CANDIDATES_REPORTED]]},
        )
    return _resolved(query, best)
