"""Data models for Rule-Based Detectors (P3) and downstream P4 handoff.

Defines structured representations of detected identifiers, their offsets,
categories, confidence, provenance, and aggregate results.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class FindingCategory(str, Enum):
    """Broad categories for detected identifiers."""
    INSTITUTIONAL = "institutional"
    EMAIL = "email"
    PHONE = "phone"
    SENSITIVE = "sensitive"
    FINANCIAL = "financial"


@dataclass
class Finding:
    """Represents an individual sensitive identifier detected by P3 rules.

    Attributes:
        finding_id: Unique identifier for the finding.
        detector: Name of the detector or technique (default 'rule').
        category: High-level category ('institutional', 'email', 'phone', 'sensitive', 'financial').
        identifier_type: Granular identifier label (e.g. 'EMP', 'DIR', 'SSN', 'CARD_NUMBER').
        value: The detected identifier string.
        start_offset: 0-indexed starting character offset in the source block's text.
        end_offset: 0-indexed ending character offset in the source block's text.
        text_block_id: ID of the source TextBlock.
        confidence: Confidence score between 0.0 and 1.0.
        context: Contextual text snippet surrounding the detected value for auditability.
        metadata: Detector-specific attributes (e.g. validation passed, card brand, prefix).
    """

    finding_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    detector: str = "rule"
    category: str = FindingCategory.SENSITIVE.value
    identifier_type: str = ""
    value: str = ""
    start_offset: int = 0
    end_offset: int = 0
    text_block_id: Optional[str] = None
    confidence: float = 1.0
    context: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert Finding to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Finding:
        """Instantiate Finding from a dictionary."""
        return cls(**data)


@dataclass
class FindingsResult:
    """Aggregated container for all findings produced across a document.

    Attributes:
        source_file: Original file path or filename.
        findings: List of validated, deduplicated Finding objects.
        total_findings: Total count of validated findings.
        findings_by_category: Breakdown count of findings per category.
        suppressed_count: Count of candidate detections discarded by false-positive filters.
        metadata: Pipeline-level execution metadata (rules evaluated, runtime, etc.).
    """

    source_file: str = ""
    findings: List[Finding] = field(default_factory=list)
    total_findings: int = 0
    findings_by_category: Dict[str, int] = field(default_factory=dict)
    suppressed_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert FindingsResult to a JSON-serializable dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Serialize FindingsResult to formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FindingsResult:
        """Instantiate FindingsResult from a dictionary."""
        findings_raw = data.get("findings", [])
        findings = [
            Finding.from_dict(f) if isinstance(f, dict) else f
            for f in findings_raw
        ]
        return cls(
            source_file=data.get("source_file", ""),
            findings=findings,
            total_findings=data.get("total_findings", len(findings)),
            findings_by_category=data.get("findings_by_category", {}),
            suppressed_count=data.get("suppressed_count", 0),
            metadata=data.get("metadata", {}),
        )
