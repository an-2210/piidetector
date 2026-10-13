"""Configuration for the P4 NER + fusion stage."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any, Dict, Mapping, Optional, Tuple


@dataclass
class P4Config:
    """Tunable P4 settings. Defaults are safe for production runs.

    Attributes:
        enable_spacy: Use Presidio + spaCy as an NER backend.
        spacy_model: spaCy pipeline name. Use "en_core_web_trf" for the
            transformer model (slower, usually more accurate).
        enable_gliner: Use GLiNER zero-shot NER (person, address, organization).
        gliner_model: Hugging Face id of the GLiNER checkpoint.
        gliner_threshold: GLiNER minimum score before a span is considered.
        defer_structured_to_rules: When True, Presidio's structured pattern
            recognizers (email, phone, SSN, card, ...) are not run, because P3
            owns them. When False, standalone demos keep them on.
        confidence_threshold: Minimum final confidence for a Finding to be kept.
        rule_confidence: Fixed confidence for rule-detector findings.
        agreement_boost: Added per extra distinct source on a merged span.
        ambiguity_penalty: Multiplier applied to ambiguous PERSON/ORG labels.
        block_weights: Confidence multiplier per block kind. Down-weights
            tables and image OCR relative to prose.
        id_like_weight: Multiplier for spans that look like identifiers.
        priority_sections: Heading fragments whose findings get a boost
            (the case-document prose sections).
        priority_boost: Confidence added to findings in priority sections.
        enable_linking: Run entity resolution to assign identity_id.
        emit_debug: Keep below-threshold candidates in the debug output.
    """

    enable_spacy: bool = True
    spacy_model: str = "en_core_web_lg"
    # Off by default: on the sample set GLiNER scores identically to spaCy alone
    # (see eval/results) while adding torch and an ~800 MB model. Opt in per run.
    enable_gliner: bool = False
    gliner_model: str = "urchade/gliner_small-v2.1"
    gliner_threshold: float = 0.4
    defer_structured_to_rules: bool = True
    confidence_threshold: float = 0.5
    rule_confidence: float = 0.95
    agreement_boost: float = 0.05
    ambiguity_penalty: float = 0.6
    block_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "body": 1.0,
            "slide": 0.9,
            "image_ocr": 0.8,
            # Tables carry real roster names, so they are down-weighted, not
            # suppressed. At 0.5 almost every table name fell below threshold.
            "table": 0.8,
        }
    )
    id_like_weight: float = 0.5
    priority_sections: Tuple[str, ...] = ("16.5", "16.8")
    priority_boost: float = 0.05
    enable_linking: bool = True
    emit_debug: bool = False
    # Deterministic street-address pattern (see src/pii/address.py).
    enable_address_pattern: bool = True
    address_street_suffixes: Tuple[str, ...] = (
        "Road", "Rd", "Street", "St", "Avenue", "Ave", "Way", "Lane", "Ln",
        "Close", "Crescent", "Cres", "Drive", "Boulevard", "Blvd", "Estate",
        "Layout", "Nagar", "Marg", "Highway", "Hwy", "Terrace",
    )
    address_base_confidence: float = 0.6
    address_house_bonus: float = 0.15
    address_tail_bonus: float = 0.10
    address_cue_bonus: float = 0.15
    # ORG false-positive filter (see disambiguate.org_false_positive_reason).
    org_filter_enabled: bool = True
    org_generic_words: Tuple[str, ...] = (
        "Audit", "Finance", "Legal", "Compliance", "HR", "Risk", "Operations",
        "Security", "Treasury", "Procurement", "Management", "Governance", "IT",
        "Committee", "Board", "Department", "Team", "Unit", "Function", "Office",
    )
    org_role_patterns: Tuple[str, ...] = (
        r"^Head of\b",
        r"^Director of\b",
        r"^Manager of\b",
        r"^Chief\b.*\bOfficer$",
        r"^Deputy\b",
    )
    org_unit_pattern: str = (
        r"^(?:the\s+)?(?:[A-Za-z][\w-]*\s+){0,3}(?:Committee|Board|Department|Team|Function|Office|Unit)$"
    )
    pii_field_labels: Tuple[str, ...] = (
        "SSN", "PAN", "DOB", "TIN", "PESEL", "Email", "Phone", "IBAN",
        "Card", "Account", "Passport", "Tax ID",
    )
    # Table column headers that mark a cell as a person (no legal suffix allowed).
    person_column_headers: Tuple[str, ...] = (
        "name", "full name", "employee", "employee name", "contact", "owner", "applicant", "staff",
    )
    # False: ORG is used for disambiguation and relabelling, then dropped from output.
    emit_org: bool = True
    # Use the P3 detector (src/pii/p3_adapter.py) when no src.pii.rules package exists.
    use_p3: bool = True
    # Safety net: drop rule findings that overlap IGNORE_PATTERNS (e.g. the digits in RSK-2024-0031).
    apply_ignore_to_rules: bool = True

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "P4Config":
        """Build a config from a plain dict, ignoring nothing silently.

        Unknown keys raise TypeError so a typo in the pipeline call is visible.
        """
        if data is None:
            return cls()
        if isinstance(data, P4Config):
            return data
        values = dict(data)
        for field_info in fields(cls):
            if isinstance(field_info.default, tuple) and field_info.name in values:
                values[field_info.name] = tuple(values[field_info.name])
        return cls(**values)
