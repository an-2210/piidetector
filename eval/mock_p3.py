"""Stand-in for the P3 rule detector, used only by the evaluation's "NER + mock P3" mode.

It emits the structured types P3 owns (EMAIL, EMP_ID) with a regex, the same
patterns the tests use. Scores from this mode measure P4 with a simple rule
detector, not the real P3.
"""

from __future__ import annotations

import re
from typing import List

from src.models.text_block import TextBlock
from src.pii.contracts import Finding

_PATTERNS = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "EMAIL"),
    (re.compile(r"\bEMP-\d{4,}\b"), "EMP_ID"),
)


class MockRegexP3:
    """Regex rule detector. Stateless and deterministic."""

    def detect(self, blocks: List[TextBlock]) -> List[Finding]:
        findings: List[Finding] = []
        for block in blocks:
            for pattern, pii_type in _PATTERNS:
                for match in pattern.finditer(block.text or ""):
                    findings.append(
                        Finding.from_block(
                            block, match.start(), match.end(), pii_type,
                            "rule", 0.99, ["rule:mock_p3"],
                        )
                    )
        return findings
