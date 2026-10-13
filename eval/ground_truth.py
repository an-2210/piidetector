"""Loader and validator for the hand-labelled evaluation set.

The schema lives in `ground_truth.schema.json`. This loader enforces the same
rules in code, so a bad label fails with a clear message before any run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from src.pii.contracts import PII_TYPES

SOURCE_KINDS = ("body", "table", "slide", "image_ocr")
DECOY_KINDS = (
    "rsk_ref", "usd_amount", "policy_date", "grp_ref", "org_contains_person", "committee_title",
    "title_role", "sentence_start_word", "month_name", "place_non_address",
    "org_generic_word", "org_role_phrase", "org_pii_label", "org_unit_phrase", "other",
)


class GroundTruthError(ValueError):
    """Raised when the ground-truth file breaks the schema."""


@dataclass(frozen=True)
class GTLabel:
    file: str
    page: Optional[int]
    source_kind: str
    text: str
    pii_type: str
    identity: Optional[str] = None
    span: Optional[Tuple[int, int]] = None


@dataclass(frozen=True)
class GTDecoy:
    file: str
    page: Optional[int]
    text: str
    kind: str = "other"
    not_type: Optional[str] = None


@dataclass
class GroundTruth:
    labels: List[GTLabel] = field(default_factory=list)
    decoys: List[GTDecoy] = field(default_factory=list)

    @property
    def files(self) -> List[str]:
        return sorted({label.file for label in self.labels} | {d.file for d in self.decoys})


def _check_location(value, where: str) -> Optional[int]:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise GroundTruthError(f"{where}: page must be a positive integer or null, got {value!r}")
    return value


def _parse_label(raw: dict, where: str) -> GTLabel:
    required = ("file", "page", "source_kind", "text", "pii_type")
    for key in required:
        if key not in raw:
            raise GroundTruthError(f"{where}: missing '{key}'")
    unknown = set(raw) - set(required) - {"identity", "span"}
    if unknown:
        raise GroundTruthError(f"{where}: unknown keys {sorted(unknown)}")
    if raw["pii_type"] not in PII_TYPES:
        raise GroundTruthError(f"{where}: pii_type {raw['pii_type']!r} is not in PII_TYPES")
    if raw["source_kind"] not in SOURCE_KINDS:
        raise GroundTruthError(f"{where}: source_kind {raw['source_kind']!r} must be one of {SOURCE_KINDS}")
    if not isinstance(raw["text"], str) or not raw["text"].strip():
        raise GroundTruthError(f"{where}: text must be a non-empty string")
    identity = raw.get("identity")
    if identity is not None and raw["pii_type"] != "PERSON":
        raise GroundTruthError(f"{where}: identity groups are only valid for PERSON")
    span = raw.get("span")
    if span is not None:
        if (
            not isinstance(span, list)
            or len(span) != 2
            or not all(isinstance(x, int) and x >= 0 for x in span)
            or not span[0] < span[1]
        ):
            raise GroundTruthError(f"{where}: span must be [start, end] with 0 <= start < end")
        span = (span[0], span[1])
    return GTLabel(
        file=raw["file"],
        page=_check_location(raw["page"], where),
        source_kind=raw["source_kind"],
        text=raw["text"],
        pii_type=raw["pii_type"],
        identity=identity,
        span=span,
    )


def _parse_decoy(raw: dict, where: str) -> GTDecoy:
    for key in ("file", "page", "text"):
        if key not in raw:
            raise GroundTruthError(f"{where}: missing '{key}'")
    unknown = set(raw) - {"file", "page", "text", "kind", "not_type"}
    if unknown:
        raise GroundTruthError(f"{where}: unknown keys {sorted(unknown)}")
    kind = raw.get("kind", "other")
    if kind not in DECOY_KINDS:
        raise GroundTruthError(f"{where}: kind {kind!r} must be one of {DECOY_KINDS}")
    not_type = raw.get("not_type")
    if not_type is not None and not_type not in PII_TYPES:
        raise GroundTruthError(f"{where}: not_type {not_type!r} is not in PII_TYPES")
    return GTDecoy(
        file=raw["file"],
        page=_check_location(raw["page"], where),
        text=raw["text"],
        kind=kind,
        not_type=not_type,
    )


def load_ground_truth(path: Path) -> GroundTruth:
    """Load and validate a ground-truth JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        raise GroundTruthError("schema_version must be 1")
    if not isinstance(data.get("labels"), list):
        raise GroundTruthError("'labels' must be a list")
    labels = [_parse_label(raw, f"labels[{i}]") for i, raw in enumerate(data["labels"])]
    decoys = [_parse_decoy(raw, f"decoys[{i}]") for i, raw in enumerate(data.get("decoys", []))]
    return GroundTruth(labels=labels, decoys=decoys)
