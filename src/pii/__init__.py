"""PII detection: shared contracts (P3/P4 seam) and the P4 NER + fusion stage."""

from src.pii.contracts import (
    IGNORE_PATTERNS,
    NER_PREFERRED_TYPES,
    PII_TYPES,
    Finding,
    RuleDetector,
)

__all__ = [
    "Finding",
    "IGNORE_PATTERNS",
    "NER_PREFERRED_TYPES",
    "PII_TYPES",
    "RuleDetector",
]
