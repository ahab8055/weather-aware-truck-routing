"""Shared risk levels and the numeric score used for average risk."""

from enum import IntEnum
from types import MappingProxyType
from typing import Mapping


class RiskLevel(IntEnum):
    """Ordered risk levels; a higher value means a more dangerous condition."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4


# Score used for distance-weighted average risk. NO_TRAVEL is deliberately
# absent: it is a hard stop, not a point on the averaging scale.
RISK_SCORES: Mapping[RiskLevel, int] = MappingProxyType(
    {
        RiskLevel.LOW: 0,
        RiskLevel.MODERATE: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.SEVERE: 3,
    }
)


def risk_score(level: RiskLevel) -> int:
    """Return the averaging score for a level. Raises ValueError for NO_TRAVEL."""
    try:
        return RISK_SCORES[level]
    except KeyError:
        raise ValueError(f"{level.name} has no numeric risk score") from None
