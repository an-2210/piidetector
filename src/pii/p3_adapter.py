"""Adapter from P3 (src/detectors, another contributor's code) to the P4 contract.

P3 emits `src.models.finding.Finding` objects with its own field names and
identifier types. This module converts them to `src.pii.contracts.Finding`,
so P4 can consume P3 without any change to P3's code.

Ownership: P3 structured identifiers are authoritative (`owner="p3"`). P3's
ADDRESS is a structural match that often stops before the locality, so it is
left unowned and P4's fuller address pattern or NER can extend it.

INTERNAL_REF is P3's suppression marker, not PII, so it is dropped.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from src.models.text_block import TextBlock
from src.pii.contracts import Finding

# P3 identifier_type -> PII_TYPES label.
P3_TO_PII: Dict[str, str] = {
    "EMP": "EMP_ID",
    "DIR": "DIR_ID",
    "MER-IN": "MER_IN_ID",
    "MER-PH": "MER_PH_ID",
    "EMAIL": "EMAIL",
    "PHONE": "PHONE",
    "SSN": "SSN",
    "PAN": "PAN",
    "PASSPORT": "PASSPORT",
    "TIN": "TIN",
    "PSEF": "PSEF",
    "CARD_NUMBER": "CARD_NUMBER",
    "ACCOUNT_LAST4": "ACCOUNT_LAST4",
    "DOB": "DOB",
    "ADDRESS": "ADDRESS",
}

# P3 identifier types that are suppression markers, not PII.
P3_NOT_PII = frozenset({"INTERNAL_REF"})

# Structured identifiers P3 owns. ADDRESS is deliberately absent (see module docstring).
P3_OWNED = frozenset(
    label for label in P3_TO_PII.values() if label != "ADDRESS"
)

SOURCE = "rule:p3"


class P3RuleAdapter:
    """Implements the P4 `RuleDetector` protocol on top of P3's `RuleBasedDetector`."""

    name = "p3"

    def __init__(self, detector: Optional[Any] = None) -> None:
        if detector is None:
            from src.detectors.pipeline import RuleBasedDetector

            detector = RuleBasedDetector()
        self._detector = detector
        self.last_stats: Dict[str, int] = {}

    def detect(self, blocks: Sequence[TextBlock]) -> List[Finding]:
        blocks = list(blocks)
        result = self._detector.detect_blocks(blocks, source_file="")
        by_id = {b.block_id: b for b in blocks}
        findings: List[Finding] = []
        dropped = unknown = missing_block = 0
        for raw in result.findings:
            if raw.identifier_type in P3_NOT_PII:
                dropped += 1
                continue
            pii_type = P3_TO_PII.get(raw.identifier_type)
            if pii_type is None:
                unknown += 1
                continue
            block = by_id.get(raw.text_block_id)
            if block is None:
                missing_block += 1
                continue
            findings.append(
                Finding.from_block(
                    block,
                    raw.start_offset,
                    raw.end_offset,
                    pii_type,
                    "rule",
                    raw.confidence,
                    [SOURCE],
                    owner="p3" if pii_type in P3_OWNED else None,
                )
            )
        self.last_stats = {
            "p3_raw": len(result.findings),
            "p3_suppressed_by_p3": result.suppressed_count,
            "p3_not_pii_dropped": dropped,
            "p3_unknown_type": unknown,
            "p3_missing_block": missing_block,
        }
        return findings


def get_detector() -> P3RuleAdapter:
    """Factory used by `src.pii.registry` to discover P3 without a hard import."""
    return P3RuleAdapter()
