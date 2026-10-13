"""Rule-Based Detectors pipeline and orchestrator (P3).

Applies deterministic regex rules and context-aware validators to TextBlocks,
filters false positives, resolves span conflicts, and produces Finding objects
conforming to the P4 downstream interface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.detectors.filter import FalsePositiveFilter
from src.detectors.patterns import (
    ACCOUNT_ENDING_PATTERN,
    ACCOUNT_LAST4_PATTERN,
    ACCOUNT_PREFIX_PATTERN,
    ADDRESS_PATTERN,
    CARD_PATTERN,
    DIR_PATTERN,
    DOB_PATTERN,
    EMAIL_PATTERN,
    EMP_PATTERN,
    MER_IN_PATTERN,
    MER_PH_PATTERN,
    PAN_PATTERN,
    PASSPORT_CONTEXT_PATTERN,
    PASSPORT_STANDALONE_PATTERN,
    PESEL_CONTEXT_PATTERN,
    PHONE_CUE_PATTERN,
    PESEL_PATTERN,
    PHONE_PATTERN,
    PSEF_PATTERN,
    SSN_PATTERN,
    TIN_PATTERN,
)
from src.detectors.validators import (
    luhn_checksum,
    trim_punctuation_offsets,
    validate_international_phone,
    validate_pan,
    validate_pesel_checksum,
    validate_pesel_date,
    validate_phone,
    validate_ssn,
    validate_tin,
)
from src.models.finding import Finding, FindingCategory, FindingsResult
from src.models.text_block import TextBlock

logger = logging.getLogger(__name__)


class RuleBasedDetector:
    """Core P3 detector coordinating rule execution and false-positive controls."""

    def __init__(self, filter_engine: Optional[FalsePositiveFilter] = None) -> None:
        self.filter = filter_engine or FalsePositiveFilter()

    def _extract_context(self, text: str, start: int, end: int, window: int = 35) -> str:
        """Extract a minimal surrounding context window for audit trails."""
        c_start = max(0, start - window)
        c_end = min(len(text), end + window)
        return text[c_start:c_end].replace("\n", " ").strip()

    # --------------------------------------------------------------------------
    # 1. Institutional Identifiers
    # --------------------------------------------------------------------------
    def detect_institutional(self, block: TextBlock) -> List[Finding]:
        findings: List[Finding] = []
        text = block.text or ""

        # EMP
        for m in EMP_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.INSTITUTIONAL.value,
                    identifier_type="EMP",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"pattern": "EMP"},
                ))

        # DIR
        for m in DIR_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.INSTITUTIONAL.value,
                    identifier_type="DIR",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"pattern": "DIR"},
                ))

        # MER-IN
        for m in MER_IN_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.INSTITUTIONAL.value,
                    identifier_type="MER-IN",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"jurisdiction": "IN", "pattern": "MER-IN"},
                ))

        # MER-PH
        for m in MER_PH_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.INSTITUTIONAL.value,
                    identifier_type="MER-PH",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"jurisdiction": "PH", "pattern": "MER-PH"},
                ))

        return findings

    # --------------------------------------------------------------------------
    # 2. Email Addresses
    # --------------------------------------------------------------------------
    def detect_email(self, block: TextBlock) -> List[Finding]:
        findings: List[Finding] = []
        text = block.text or ""

        for m in EMAIL_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.EMAIL.value,
                    identifier_type="EMAIL",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"domain": val.split("@")[-1] if "@" in val else ""},
                ))

        return findings

    # --------------------------------------------------------------------------
    # 3. Global Phone Numbers
    # --------------------------------------------------------------------------
    def detect_phone(self, block: TextBlock) -> List[Finding]:
        findings: List[Finding] = []
        text = block.text or ""

        for m in PHONE_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if not val:
                continue

            # Exclude false positives: dates, SSN formats, TIN formats
            if SSN_PATTERN.fullmatch(val) or TIN_PATTERN.fullmatch(val):
                continue

            # A bare 11-digit run is usually an ID (PESEL, account, reference), not a phone.
            # Accept it only after a phone cue, or with an explicit +/00 prefix in the text
            # that phonenumbers validates.
            if val.isdigit() and len(val) == 11:
                before = text[max(0, s - 25):s]
                cued = bool(PHONE_CUE_PATTERN.search(before))
                prefixed = before.rstrip().endswith(("+", "00"))
                if not (cued or (prefixed and validate_international_phone(val))):
                    continue

            if validate_phone(val):
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.PHONE.value,
                    identifier_type="PHONE",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"is_international": val.startswith("+")},
                ))

        return findings

    # --------------------------------------------------------------------------
    # 4. Sensitive Identifiers
    # --------------------------------------------------------------------------
    def detect_sensitive(self, block: TextBlock) -> List[Finding]:
        findings: List[Finding] = []
        text = block.text or ""

        # SSN
        for m in SSN_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val and validate_ssn(val):
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.SENSITIVE.value,
                    identifier_type="SSN",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"jurisdiction": "US", "format": "AAA-GG-SSSS"},
                ))

        # Indian PAN
        for m in PAN_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val and validate_pan(val):
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.SENSITIVE.value,
                    identifier_type="PAN",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"jurisdiction": "IN", "holder_type": val[3]},
                ))

        # US TIN / EIN
        for m in TIN_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val and validate_tin(val):
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.SENSITIVE.value,
                    identifier_type="TIN",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"jurisdiction": "US", "format": "XX-XXXXXXX"},
                ))

        # Polish PESEL: a valid date is required. A valid checksum is enough on its own;
        # otherwise an explicit "PESEL" label before the number is required.
        for m in PESEL_PATTERN.finditer(text):
            val = m.group(0)
            if not validate_pesel_date(val):
                continue
            checksum_ok = validate_pesel_checksum(val)
            labelled = bool(PESEL_CONTEXT_PATTERN.search(text[max(0, m.start() - 25):m.start()]))
            if not (checksum_ok or labelled):
                continue
            findings.append(Finding(
                detector="rule",
                category=FindingCategory.SENSITIVE.value,
                identifier_type="PESEL",
                value=val,
                start_offset=m.start(),
                end_offset=m.end(),
                text_block_id=block.block_id,
                confidence=1.0 if checksum_ok else 0.8,
                context=self._extract_context(text, m.start(), m.end()),
                metadata={"jurisdiction": "PL", "checksum_valid": checksum_ok, "context_anchored": labelled},
            ))

        # PSEF
        for m in PSEF_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.SENSITIVE.value,
                    identifier_type="PSEF",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"pattern": "PSEF"},
                ))

        # Passport (contextual or standalone near keywords)
        for m in PASSPORT_CONTEXT_PATTERN.finditer(text):
            val = m.group(1)
            s = m.start(1)
            e = m.end(1)
            findings.append(Finding(
                detector="rule",
                category=FindingCategory.SENSITIVE.value,
                identifier_type="PASSPORT",
                value=val,
                start_offset=s,
                end_offset=e,
                text_block_id=block.block_id,
                context=self._extract_context(text, s, e),
                metadata={"detection_mode": "contextual"},
            ))

        # Standalone passport if passport keyword is in block
        if "passport" in text.lower():
            for m in PASSPORT_STANDALONE_PATTERN.finditer(text):
                val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
                if val:
                    # Check that it is not already captured
                    if not any(f.start_offset == s and f.end_offset == e for f in findings):
                        findings.append(Finding(
                            detector="rule",
                            category=FindingCategory.SENSITIVE.value,
                            identifier_type="PASSPORT",
                            value=val,
                            start_offset=s,
                            end_offset=e,
                            text_block_id=block.block_id,
                            context=self._extract_context(text, s, e),
                            metadata={"detection_mode": "keyword_anchored"},
                        ))

        return findings

    # --------------------------------------------------------------------------
    # 5. Financial & Account Identifiers
    # --------------------------------------------------------------------------
    def detect_financial(self, block: TextBlock) -> List[Finding]:
        findings: List[Finding] = []
        text = block.text or ""

        # Credit / Debit Card (Luhn validated)
        for m in CARD_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val and luhn_checksum(val):
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.FINANCIAL.value,
                    identifier_type="CARD_NUMBER",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"luhn_valid": True, "length": len([c for c in val if c.isdigit()])},
                ))

        # Account Number (last 4 digits or prefixed account ID)
        for m in ACCOUNT_LAST4_PATTERN.finditer(text):
            val = m.group(1)
            s = m.start(1)
            e = m.end(1)
            findings.append(Finding(
                detector="rule",
                category=FindingCategory.FINANCIAL.value,
                identifier_type="ACCOUNT_LAST4",
                value=val,
                start_offset=s,
                end_offset=e,
                text_block_id=block.block_id,
                context=self._extract_context(text, s, e),
                metadata={"format": "last_4_digits"},
            ))

        for m in ACCOUNT_ENDING_PATTERN.finditer(text):
            val = m.group(1)
            s = m.start(1)
            e = m.end(1)
            findings.append(Finding(
                detector="rule",
                category=FindingCategory.FINANCIAL.value,
                identifier_type="ACCOUNT_LAST4",
                value=val,
                start_offset=s,
                end_offset=e,
                text_block_id=block.block_id,
                context=self._extract_context(text, s, e),
                metadata={"format": "ending_in"},
            ))

        for m in ACCOUNT_PREFIX_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.FINANCIAL.value,
                    identifier_type="ACCOUNT_LAST4",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"format": "prefixed_account"},
                ))

        # Date of Birth (DOB) - Context-aware
        for m in DOB_PATTERN.finditer(text):
            val = m.group(1)
            s = m.start(1)
            e = m.end(1)
            findings.append(Finding(
                detector="rule",
                category=FindingCategory.FINANCIAL.value,
                identifier_type="DOB",
                value=val,
                start_offset=s,
                end_offset=e,
                text_block_id=block.block_id,
                context=self._extract_context(text, s, e),
                metadata={"context_anchored": True},
            ))

        # Physical Address
        for m in ADDRESS_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category=FindingCategory.FINANCIAL.value,
                    identifier_type="ADDRESS",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"structural_address": True},
                ))

        return findings

    # --------------------------------------------------------------------------
    # Block & Document Level Detection
    # --------------------------------------------------------------------------
    def detect_block(self, block: TextBlock) -> Tuple[List[Finding], int]:
        """Run all rule detectors on a single TextBlock and filter false positives.

        Returns:
            Tuple of (accepted_findings, suppressed_count).
        """
        if not block or not block.text or not block.text.strip():
            return [], 0

        raw_candidates: List[Finding] = []
        raw_candidates.extend(self.detect_institutional(block))
        raw_candidates.extend(self.detect_email(block))
        raw_candidates.extend(self.detect_phone(block))
        raw_candidates.extend(self.detect_sensitive(block))
        raw_candidates.extend(self.detect_financial(block))
        raw_candidates.extend(self.detect_internal_references(block))

        accepted, suppressed = self.filter.filter_findings(raw_candidates, full_text=block.text)
        return accepted, suppressed

    def detect_internal_references(self, block: TextBlock) -> List[Finding]:
        """Detect internal non-sensitive references to be explicitly routed to false-positive suppression."""
        findings: List[Finding] = []
        text = block.text or ""
        from src.detectors.patterns import INTERNAL_REF_PATTERN
        for m in INTERNAL_REF_PATTERN.finditer(text):
            val, s, e = trim_punctuation_offsets(text, m.start(), m.end())
            if val:
                findings.append(Finding(
                    detector="rule",
                    category="internal_reference",
                    identifier_type="INTERNAL_REF",
                    value=val,
                    start_offset=s,
                    end_offset=e,
                    text_block_id=block.block_id,
                    context=self._extract_context(text, s, e),
                    metadata={"suppression_target": True},
                ))
        return findings

    def detect_blocks(
        self,
        blocks: List[TextBlock],
        source_file: str = "",
    ) -> FindingsResult:
        """Run rule detectors across a sequence of TextBlocks and return aggregated result."""
        all_findings: List[Finding] = []
        total_suppressed = 0
        cat_counts: Dict[str, int] = {}

        # Preserve reading order when sorting blocks
        sorted_blocks = sorted(blocks, key=lambda b: (b.reading_order, b.page_number or 0, b.slide_number or 0))

        for block in sorted_blocks:
            block_findings, suppressed = self.detect_block(block)
            total_suppressed += suppressed
            all_findings.extend(block_findings)

        for finding in all_findings:
            cat = finding.category
            cat_counts[cat] = cat_counts.get(cat, 0) + 1

        return FindingsResult(
            source_file=source_file,
            findings=all_findings,
            total_findings=len(all_findings),
            findings_by_category=cat_counts,
            suppressed_count=total_suppressed,
            metadata={
                "blocks_analyzed": len(blocks),
                "detector": "rule_based_p3",
            },
        )


def run_detectors_pipeline(
    blocks: List[TextBlock],
    source_file: str = "",
) -> FindingsResult:
    """Convenience functional entry point for P3 detection."""
    detector = RuleBasedDetector()
    return detector.detect_blocks(blocks, source_file=source_file)
