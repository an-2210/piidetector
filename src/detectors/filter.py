"""False-positive suppression and span conflict resolution engine (P3)."""

from __future__ import annotations

import re
from typing import List, Set, Tuple

from src.detectors.patterns import (
    CURRENCY_AMOUNT_PATTERN,
    INTERNAL_REF_PATTERN,
    POLICY_DATE_KEYWORDS,
    RATIO_PERCENT_PATTERN,
)
from src.models.finding import Finding


# Priority order for resolving conflicting overlapping spans on the same text block
# Higher priority detectors supersede lower priority / generic detectors
DETECTOR_PRIORITY = {
    "CARD_NUMBER": 100,
    "SSN": 90,
    "PESEL": 88,
    "PAN": 85,
    "PASSPORT": 80,
    "TIN": 75,
    "PSEF": 70,
    "EMP": 65,
    "DIR": 60,
    "MER-IN": 60,
    "MER-PH": 60,
    "EMAIL": 55,
    "PHONE": 50,
    "DOB": 45,
    "ACCOUNT_LAST4": 40,
    "ADDRESS": 30,
}


class FalsePositiveFilter:
    """Explicit, testable false-positive control and deduplication component."""

    def __init__(self) -> None:
        pass

    def is_suppressed_reference(self, value: str) -> bool:
        """Check if value matches internal reference schemes (RSK-, ISS-, INC-, GRP-POL-)."""
        val_clean = value.strip()
        return bool(INTERNAL_REF_PATTERN.search(val_clean))

    def is_currency_or_ratio_context(self, value: str, context: str) -> bool:
        """Check if value is a financial amount, percentage, or ratio rather than an identifier."""
        # Standalone ratio check
        if RATIO_PERCENT_PATTERN.fullmatch(value.strip()):
            return True

        # Check if surrounding context indicates currency
        if "$" in context or "USD" in context.upper() or "EUR" in context.upper():
            clean_digits = re.sub(r"[^\d]", "", value)
            # If the detected value is just the number portion of the currency figure
            if re.search(r"[\$€£]\s*" + re.escape(value), context):
                return True
            if re.search(re.escape(value) + r"\s*(?:USD|EUR|GBP|INR)", context, re.IGNORECASE):
                return True

        return False

    def is_policy_date(self, context: str) -> bool:
        """Check if candidate date is in a policy / governance context."""
        return bool(POLICY_DATE_KEYWORDS.search(context))

    def resolve_overlapping_spans(self, findings: List[Finding]) -> List[Finding]:
        """Resolve overlapping text spans by selecting the higher priority finding."""
        if not findings:
            return []

        # Sort findings by start offset ascending, then by priority descending
        sorted_findings = sorted(
            findings,
            key=lambda f: (
                f.start_offset,
                -DETECTOR_PRIORITY.get(f.identifier_type, 0),
                -(f.end_offset - f.start_offset),
            ),
        )

        resolved: List[Finding] = []
        for candidate in sorted_findings:
            if not resolved:
                resolved.append(candidate)
                continue

            last = resolved[-1]
            # Check for overlap within the same block
            if candidate.text_block_id == last.text_block_id and candidate.start_offset < last.end_offset:
                last_priority = DETECTOR_PRIORITY.get(last.identifier_type, 0)
                cand_priority = DETECTOR_PRIORITY.get(candidate.identifier_type, 0)

                if cand_priority > last_priority:
                    resolved[-1] = candidate
                elif cand_priority == last_priority:
                    # Longer span wins if equal priority
                    if (candidate.end_offset - candidate.start_offset) > (last.end_offset - last.start_offset):
                        resolved[-1] = candidate
                # Otherwise, keep existing 'last' and discard candidate
            else:
                resolved.append(candidate)

        return resolved

    def filter_findings(
        self,
        findings: List[Finding],
        full_text: str = "",
    ) -> Tuple[List[Finding], int]:
        """Apply all false-positive suppression rules, span de-conflicting, and deduplication.

        Returns:
            Tuple of (accepted_findings, count_of_suppressed_candidates).
        """
        accepted: List[Finding] = []
        suppressed_count = 0
        seen_keys: Set[Tuple[str, int, int, str, str]] = set()

        for finding in findings:
            val = finding.value
            ctx = finding.context or full_text[
                max(0, finding.start_offset - 30): min(len(full_text), finding.end_offset + 30)
            ]

            # 1. Suppress internal tracking references (RSK-, ISS-, INC-, GRP-POL-)
            if self.is_suppressed_reference(val) or finding.category == "internal_reference":
                suppressed_count += 1
                continue

            # 2. Suppress currency amounts and financial ratios
            if self.is_currency_or_ratio_context(val, ctx):
                suppressed_count += 1
                continue

            # 3. Suppress policy / governance dates misclassified as DOB
            if finding.identifier_type == "DOB" and self.is_policy_date(ctx):
                suppressed_count += 1
                continue

            # 4. Deduplicate identical findings. The type is part of the key, so two rules
            # matching the same span (e.g. PHONE and PESEL) reach priority resolution
            # instead of the first one silently winning.
            key = (finding.text_block_id or "", finding.start_offset, finding.end_offset, val, finding.identifier_type)
            if key in seen_keys:
                suppressed_count += 1
                continue
            seen_keys.add(key)

            accepted.append(finding)

        # 5. Resolve overlapping spans
        pre_resolve_count = len(accepted)
        resolved = self.resolve_overlapping_spans(accepted)
        suppressed_count += (pre_resolve_count - len(resolved))

        return resolved, suppressed_count
