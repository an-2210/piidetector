"""Shared helpers for P4 tests: building blocks and loading the mock P3 fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Tuple

from src.models.text_block import TextBlock
from src.pii.contracts import Finding

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "mock_p3_findings.json"


def make_block(text: str, **kwargs) -> TextBlock:
    """Build a TextBlock with sensible defaults for P4 tests."""
    defaults = dict(
        block_id=kwargs.pop("block_id", f"blk-{abs(hash(text)) % 10**8}"),
        source_file="casefile.docx",
        source_type="DOCX",
        block_type="body",
        text=text,
        reading_order=0,
    )
    defaults.update(kwargs)
    return TextBlock(**defaults)


def load_mock_p3() -> Tuple[List[TextBlock], List[Finding]]:
    """Load the fixture, returning TextBlocks and the mock rule Findings bound to them.

    Each fixture block gets a stable test block_id (the `ref`). Each finding's
    `text` is checked against the block text, so a bad offset fails loudly here.
    """
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    blocks: List[TextBlock] = []
    by_ref = {}
    for raw in data["blocks"]:
        block = TextBlock(
            block_id=raw["ref"],
            source_file=raw["source_file"],
            source_type=raw["source_type"],
            block_type=raw["block_type"],
            text=raw["text"],
            content=raw.get("content"),
            page_number=raw.get("page_number"),
            slide_number=raw.get("slide_number"),
            section_or_heading=raw.get("section_or_heading"),
            reading_order=raw["reading_order"],
            metadata=raw.get("metadata", {}),
        )
        blocks.append(block)
        by_ref[raw["ref"]] = block

    findings: List[Finding] = []
    for raw in data["findings"]:
        block = by_ref[raw["ref"]]
        assert block.text[raw["start"] : raw["end"]] == raw["text"], raw
        findings.append(
            Finding.from_block(
                block,
                raw["start"],
                raw["end"],
                raw["pii_type"],
                raw["detector"],
                raw["confidence"],
                raw["sources"],
            )
        )
    return blocks, findings
