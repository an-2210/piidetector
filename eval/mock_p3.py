"""Stand-in for the P3 rule detector, used only by the evaluation's "NER + mock P3" mode.

Emits the types a rule detector owns, with regex patterns. Every finding carries
owner="p3", so P4's fusion treats it as authoritative on overlap.

It is deliberately not the real P3. It exists to measure what a rule layer adds on
top of NER, and to exercise the fusion conflicts the real P3 will produce:
  * labelled fields ("Applicant: ...", "Home address: ..."), which may overlap NER spans,
  * an email that two patterns both match (an exact duplicate),
  * structured identifiers that NER never emits (SSN, PAN, PESEL, TIN, card and
    account last-4, DIR and MER IDs, DOB).
"""

from __future__ import annotations

import re
from typing import List, Tuple

from src.models.text_block import TextBlock
from src.pii.contracts import Finding

NAME = r"((?:[A-Z][\w.'-]*\s+){1,3}[A-Z][\w.'-]*)"
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# (pattern, pii_type, group index holding the span, source name)
PATTERNS: Tuple[Tuple["re.Pattern[str]", str, int, str], ...] = (
    (re.compile(EMAIL), "EMAIL", 0, "rule:mock_p3:email"),
    # Same email, reached through a labelled line. This is the exact duplicate.
    (re.compile(rf"Email:\s*({EMAIL})"), "EMAIL", 1, "rule:mock_p3:labelled_email"),
    (re.compile(r"\bEMP-\d{4,}\b"), "EMP_ID", 0, "rule:mock_p3:emp"),
    (re.compile(r"\bDIR-\d{5,}\b"), "DIR_ID", 0, "rule:mock_p3:dir"),
    (re.compile(r"\bMER-IN-\d{6}\b"), "MER_IN_ID", 0, "rule:mock_p3:mer_in"),
    (re.compile(r"\bMER-PH-\d{6}\b"), "MER_PH_ID", 0, "rule:mock_p3:mer_ph"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "SSN", 0, "rule:mock_p3:ssn"),
    (re.compile(r"\b(?:\d{4}[ -]){3}\d{4}\b"), "PAN", 0, "rule:mock_p3:pan"),
    (re.compile(r"card ending\s+(\d{4})\b", re.IGNORECASE), "CARD_LAST4", 1, "rule:mock_p3:card4"),
    (re.compile(r"account ending\s+(\d{4})\b", re.IGNORECASE), "ACCOUNT_LAST4", 1, "rule:mock_p3:acct4"),
    (re.compile(r"PESEL:?\s*(\d{11})\b"), "PESEL", 1, "rule:mock_p3:pesel"),
    (re.compile(r"TIN:?\s*(\d{2}-\d{7})\b"), "TIN", 1, "rule:mock_p3:tin"),
    (re.compile(r"DOB:?\s*(\d{1,2}/\d{1,2}/\d{4})\b"), "DOB", 1, "rule:mock_p3:dob"),
    # Labelled fields: the value after the label is the authoritative span.
    (re.compile(rf"(?:Applicant|Name|Employee):\s*{NAME}"), "PERSON", 1, "rule:mock_p3:labelled_name"),
    (re.compile(r"(?:Home address|Address|Office):\s*([^\n;.]+)"), "ADDRESS", 1, "rule:mock_p3:labelled_address"),
)


class MockRegexP3:
    """Regex rule detector. Stateless and deterministic."""

    def detect(self, blocks: List[TextBlock]) -> List[Finding]:
        findings: List[Finding] = []
        for block in blocks:
            text = block.text or ""
            for pattern, pii_type, group, source in PATTERNS:
                for match in pattern.finditer(text):
                    start, end = match.span(group)
                    if start < 0 or end <= start:
                        continue
                    findings.append(
                        Finding.from_block(
                            block, start, end, pii_type, "rule", 0.99, [source], owner="p3",
                        )
                    )
        return findings
