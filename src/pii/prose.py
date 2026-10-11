"""Prose-focus weighting: which blocks and spans P4 trusts more.

Body prose carries the person and organisation mentions that NER is good at.
Table cells and ID-looking tokens are noisy for NER, so their confidence is
scaled down rather than dropped outright.
"""

from __future__ import annotations

import re

from src.models.text_block import TextBlock
from src.pii.config import P4Config
from src.pii.contracts import source_kind

# Identifier-looking token: contains a digit, or is hyphenated upper-case
# (e.g. EMP-40123, RSK-2024-0031, ACME-LTD-7).
_ID_LIKE = re.compile(r"\d|^[A-Z0-9]+(?:-[A-Z0-9]+)+$")


def block_weight(block: TextBlock, config: P4Config) -> float:
    """Confidence multiplier for a block, based on its kind."""
    return float(config.block_weights.get(source_kind(block), 1.0))


def is_id_like(text: str) -> bool:
    """True when a span looks like an identifier rather than a name or organisation."""
    stripped = text.strip()
    return bool(stripped) and bool(_ID_LIKE.search(stripped))


def in_priority_section(block: TextBlock, config: P4Config) -> bool:
    """True when the block sits under one of the priority section headings."""
    heading = block.section_or_heading or ""
    section = str((block.metadata or {}).get("section", ""))
    haystack = f"{heading} {section}"
    return any(marker in haystack for marker in config.priority_sections)
