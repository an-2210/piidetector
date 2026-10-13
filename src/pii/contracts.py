"""Shared PII detection contract between P3 (rule-based) and P4 (NER + fusion).

This module is the seam between detectors. Anything that produces PII spans
must emit `Finding` objects in this shape, use labels from `PII_TYPES`, and
respect `IGNORE_PATTERNS` so that false-positive handling has one source of
truth.

Offset convention: `start` and `end` are character offsets into
`TextBlock.text` of the block named by `block_id`, half-open `[start, end)`.
`text == block.text[start:end]` must hold.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from src.models.text_block import TextBlock

# Canonical label vocabulary. Detectors must map to these labels; anything
# else is dropped by P4. Order is stable and is used for deterministic output.
PII_TYPES: Tuple[str, ...] = (
    "PERSON",
    "ORG",
    "ADDRESS",
    "EMAIL",
    "PHONE",
    "EMP_ID",
    "DIR_ID",
    "MER_IN_ID",
    "MER_PH_ID",
    "SSN",
    "PAN",
    "PASSPORT",
    "PESEL",
    "TIN",
    "CARD_LAST4",
    "ACCOUNT_LAST4",
    "DOB",
    # Added to match P3's handoff: full card numbers (Luhn-validated) and PSEF references.
    "CARD_NUMBER",
    "PSEF",
)

# Types whose boundaries and labels are decided by NER in a fusion conflict.
# Every other type is structured and is decided by the rule detector.
NER_PREFERRED_TYPES = frozenset({"PERSON", "ORG", "ADDRESS"})

# Valid `Finding.detector` values.
DETECTORS = ("rule", "ner")

# False-positive controls shared by P3 and P4. A span that overlaps any match
# is not emitted. Compile once here; import the list, don't re-declare it.
IGNORE_PATTERNS: Tuple["re.Pattern[str]", ...] = (
    # Internal reference numbers that look like identifiers but are not PII.
    re.compile(r"\bRSK-[A-Z0-9][A-Z0-9-]*\b"),
    re.compile(r"\bISS-[A-Z0-9][A-Z0-9-]*\b"),
    re.compile(r"\bINC-[A-Z0-9][A-Z0-9-]*\b"),
    re.compile(r"\bGRP-POL-[A-Z0-9][A-Z0-9-]*\b"),
    # Policy and document dates: a date that follows a policy keyword.
    re.compile(
        r"\b(?:effective|issued|revised|reviewed|review|valid until|policy)"
        r"(?:\s+date)?\s*[:\-]?\s*"
        r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}"
        r"|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    ),
    # USD amounts.
    re.compile(
        r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:[KMB]|thousand|million|billion))?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bUSD\s?\d[\d,]*(?:\.\d+)?\b"),
    # Ratios written as a:b (e.g. "3:1"). Slash form is excluded because it
    # collides with dates such as DOB.
    re.compile(r"\b\d+(?:\.\d+)?:\d+(?:\.\d+)?\b"),
)


@dataclass
class Finding:
    """One detected PII span inside one TextBlock.

    Required: block_id, start, end, text, pii_type, detector, confidence.
    `sources` names the detectors or backends that produced the span, e.g.
    "rule:p3" or "ner:spacy". `identity_id` is set only by P4 entity
    resolution, for PERSON findings.
    """

    block_id: str
    start: int
    end: int
    text: str
    pii_type: str
    detector: str
    confidence: float
    sources: List[str] = field(default_factory=list)
    identity_id: Optional[str] = None
    # Location copied from the TextBlock so downstream modules need no join.
    source_file: str = ""
    source_type: str = ""
    block_type: str = ""
    # "body" | "table" | "slide" | "image_ocr" (from block metadata provenance).
    source_kind: str = ""
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section_or_heading: Optional[str] = None
    reading_order: int = 0
    # Who is authoritative for this span. "p3": a rule detector's labelled-field or
    # structured match, which beats NER on overlap. "p4": P4's own pattern address.
    # None: no claim (the default type-based rules apply).
    owner: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-serialisable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        """Build a Finding from a dict produced by `to_dict`."""
        return cls(**data)

    @classmethod
    def from_block(
        cls,
        block: TextBlock,
        start: int,
        end: int,
        pii_type: str,
        detector: str,
        confidence: float,
        sources: Sequence[str],
        owner: Optional[str] = None,
    ) -> "Finding":
        """Create a Finding for a span of `block.text`, copying block location."""
        return cls(
            block_id=block.block_id,
            start=start,
            end=end,
            text=block.text[start:end],
            pii_type=pii_type,
            detector=detector,
            confidence=float(confidence),
            sources=list(sources),
            source_file=block.source_file,
            source_type=block.source_type,
            block_type=block.block_type,
            source_kind=source_kind(block),
            page_number=block.page_number,
            slide_number=block.slide_number,
            section_or_heading=block.section_or_heading,
            reading_order=block.reading_order,
            owner=owner,
        )


def source_kind(block: TextBlock) -> str:
    """Return the provenance kind of a block: "image_ocr", "table", "slide" or "body"."""
    if (block.metadata or {}).get("source") == "image_ocr":
        return "image_ocr"
    return block.block_type


def ignore_spans(text: str) -> List[Tuple[int, int]]:
    """Return the `[start, end)` spans in `text` matched by IGNORE_PATTERNS."""
    spans: List[Tuple[int, int]] = []
    for pattern in IGNORE_PATTERNS:
        for match in pattern.finditer(text):
            spans.append((match.start(), match.end()))
    return sorted(spans)


def overlaps_ignore(start: int, end: int, spans: Sequence[Tuple[int, int]]) -> bool:
    """True if `[start, end)` overlaps any span in `spans`."""
    return any(start < s_end and s_start < end for s_start, s_end in spans)


@runtime_checkable
class RuleDetector(Protocol):
    """Interface a rule-based (P3) detector implements.

    `detect` must be a pure function of its input. It must return Findings
    with `detector="rule"`, offsets into each block's `text`, and labels from
    `PII_TYPES`.
    """

    def detect(self, blocks: List[TextBlock]) -> List[Finding]:
        """Return rule-based Findings for the given blocks."""
        ...


_FINDING_REQUIRED = {
    "block_id": str,
    "start": int,
    "end": int,
    "text": str,
    "pii_type": str,
    "detector": str,
    "confidence": (int, float),
    "sources": list,
}


def validate_finding_dict(data: Dict[str, Any]) -> List[str]:
    """Return a list of schema problems for one serialised Finding (empty if valid)."""
    problems: List[str] = []
    for key, expected in _FINDING_REQUIRED.items():
        if key not in data:
            problems.append(f"missing field '{key}'")
        elif not isinstance(data[key], expected):
            problems.append(f"field '{key}' has type {type(data[key]).__name__}")
    if problems:
        return problems
    if data["pii_type"] not in PII_TYPES:
        problems.append(f"unknown pii_type '{data['pii_type']}'")
    if data["detector"] not in DETECTORS:
        problems.append(f"unknown detector '{data['detector']}'")
    if not 0.0 <= float(data["confidence"]) <= 1.0:
        problems.append("confidence outside [0, 1]")
    if not 0 <= data["start"] < data["end"]:
        problems.append("span must satisfy 0 <= start < end")
    identity = data.get("identity_id")
    if identity is not None and not isinstance(identity, str):
        problems.append("identity_id must be a string or null")
    return problems
