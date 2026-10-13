"""Internal linking-evidence extractor for emails and EMP-style IDs.

Used only when no P3 rule detector is available. Its output feeds entity
resolution. It is not emitted as Findings unless `defer_structured_to_rules`
is False (standalone demo). Once P3 exists, its EMAIL and EMP_ID findings are
used instead and this module is not called.
"""

from __future__ import annotations

import re
from typing import List

from src.models.text_block import TextBlock
from src.pii.contracts import Finding

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMP_ID_RE = re.compile(r"\bEMP-\d{4,}\b")

LINKING_SOURCE = "p4:linking"


def extract_evidence(blocks: List[TextBlock]) -> List[Finding]:
    """Find emails and EMP-style IDs in every block, in block order."""
    found: List[Finding] = []
    for block in blocks:
        text = block.text or ""
        if not text:
            continue
        for pattern, pii_type in ((EMAIL_RE, "EMAIL"), (EMP_ID_RE, "EMP_ID")):
            for match in pattern.finditer(text):
                found.append(
                    Finding.from_block(
                        block,
                        match.start(),
                        match.end(),
                        pii_type,
                        "rule",
                        1.0,
                        [LINKING_SOURCE],
                    )
                )
    found.sort(key=lambda f: (f.source_file, f.reading_order, f.start, f.pii_type))
    return found
