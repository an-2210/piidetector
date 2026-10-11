"""Deterministic street-address recogniser.

Pattern: optional unit + optional house number + 1-4 capitalised words + a street
suffix (from config), then optional ", Locality", optional ", City" and optional
postcode.

Emission rules:
  * A match needs a house number, a cue ("address", "lives at", ...), or a
    ", City" tail. A bare street name with none of these is not emitted.
  * A bare city or country is never emitted. spaCy LOCATION spans are used only
    to extend a match into an adjacent place name.
  * Confidence starts at a base and gains a bonus for each structural signal:
    house number, city tail, and a context cue before the match.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from src.pii.config import P4Config

UNIT = r"(?:(?:Flat|Unit|Apt|Apartment|Suite|Plot|Block)\s+[\w/-]+,?\s+)?"
HOUSE = r"(?:(?P<house>\d{1,5}[A-Za-z]?(?:[/-]\d{1,5})?)\s+)?"
NAME = r"(?P<name>(?:[A-Z][\w'’-]*\s+){0,3}[A-Z][\w'’-]*)"
LOCALITY = r"(?:,\s*(?P<locality>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,2}))?"
CITY = r"(?:,\s*(?P<city>[A-Z][\w'’-]*(?:\s+[A-Z][\w'’-]*){0,2}))?"
POSTCODE = r"(?:\s+\d{5,6})?"

CUE = re.compile(
    r"(?:home\s+address|registered\s+office|resides\s+at|residing\s+at|lives\s+at|"
    r"located\s+at|based\s+at|office\s+at|address|address\s+is)\s*[:\-]?\s*$",
    re.IGNORECASE,
)
CUE_WINDOW = 40


@dataclass(frozen=True)
class AddressSpan:
    start: int
    end: int
    text: str
    confidence: float
    has_house: bool
    has_city: bool
    has_cue: bool


def _pattern(suffixes: Sequence[str]) -> "re.Pattern[str]":
    alternatives = "|".join(re.escape(s) for s in sorted(suffixes, key=len, reverse=True))
    return re.compile(
        rf"{UNIT}{HOUSE}{NAME}\s+(?:{alternatives})\b\.?{LOCALITY}{CITY}{POSTCODE}"
    )


_CACHE: dict = {}


def find_addresses(
    text: str,
    place_spans: Sequence[Tuple[int, int]],
    config: P4Config,
) -> List[AddressSpan]:
    """Return address spans in `text`, in order. Pure function of its inputs."""
    if not config.enable_address_pattern or not text:
        return []
    key = tuple(config.address_street_suffixes)
    if key not in _CACHE:
        _CACHE[key] = _pattern(key)
    pattern = _CACHE[key]

    spans: List[AddressSpan] = []
    for match in pattern.finditer(text):
        start, end = match.start(), match.end()
        has_house = match.group("house") is not None
        has_city = match.group("city") is not None or match.group("locality") is not None
        before = text[max(0, start - CUE_WINDOW) : start]
        has_cue = CUE.search(before) is not None
        if not (has_house or has_cue or has_city):
            continue

        # Grow the span into an adjacent place name (e.g. "..., Lagos Island").
        for place_start, place_end in place_spans:
            gap = text[end:place_start]
            if 0 <= place_start - end <= 3 and gap.strip() in ("", ","):
                end = max(end, place_end)

        confidence = config.address_base_confidence
        confidence += config.address_house_bonus if has_house else 0.0
        confidence += config.address_tail_bonus if has_city else 0.0
        confidence += config.address_cue_bonus if has_cue else 0.0
        spans.append(
            AddressSpan(
                start=start,
                end=end,
                text=text[start:end],
                confidence=round(min(confidence, 0.95), 4),
                has_house=has_house,
                has_city=has_city,
                has_cue=has_cue,
            )
        )
    return spans
