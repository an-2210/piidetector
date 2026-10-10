"""Tests for python-docx based DocxExtractor."""

from pathlib import Path
import docx
import pytest
from src.extractors.docx_extractor import DocxExtractor
from src.models.text_block import BlockType, SourceType


def test_docx_extraction_basic(sample_docx_with_ground_truth):
    docx_path, gt = sample_docx_with_ground_truth
    extractor = DocxExtractor()
    result = extractor.extract(docx_path)

    assert result.source_file == docx_path.name
    assert result.source_type == SourceType.DOCX.value
    assert result.total_blocks > 0
    assert len(result.errors) == 0


def test_docx_table_extraction(sample_docx_with_ground_truth):
    docx_path, gt = sample_docx_with_ground_truth
    extractor = DocxExtractor()
    result = extractor.extract(docx_path)

    table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE.value]
    assert len(table_blocks) == 1, "Expected 1 table in DOCX"

    tbl = table_blocks[0]
    assert tbl.content is not None
    assert len(tbl.content) == 3  # 3 rows
    assert len(tbl.content[0]) == 4  # 4 columns
    assert "Timestamp" in tbl.text
    assert "10.0.4.15" in tbl.text
    assert tbl.metadata["row_count"] == 3
    assert tbl.metadata["col_count"] == 4


def test_docx_interleaved_reading_order(sample_docx_with_ground_truth):
    """Verify that paragraphs and tables are extracted in exact document sequence."""
    docx_path, gt = sample_docx_with_ground_truth
    extractor = DocxExtractor(include_headers_footers=False)
    result = extractor.extract(docx_path)

    # In our fixture:
    # 0: Heading 1 ("Security Incident Analysis")
    # 1: Paragraph 1 ("Suspicious outbound C2...")
    # 2: Table
    # 3: Heading 2 ("Containment Protocols")
    # 4: Paragraph 2 ("Network isolation applied...")
    types = [b.block_type for b in result.blocks]
    assert types == ["body", "body", "table", "body", "body"]

    # Check reading order indices are strictly sequential 0, 1, 2, 3, 4
    reading_orders = [b.reading_order for b in result.blocks]
    assert reading_orders == list(range(len(result.blocks)))


def test_docx_headers_and_footers(sample_docx_with_ground_truth):
    docx_path, gt = sample_docx_with_ground_truth
    extractor = DocxExtractor(include_headers_footers=True)
    result = extractor.extract(docx_path)

    headers = [b for b in result.blocks if b.metadata.get("is_header")]
    footers = [b for b in result.blocks if b.metadata.get("is_footer")]

    assert len(headers) >= 1
    assert "CONFIDENTIAL" in headers[0].text
    assert len(footers) >= 1
    assert "IR-2026-99" in footers[0].text


def test_docx_heading_context_tracking(sample_docx_with_ground_truth):
    docx_path, gt = sample_docx_with_ground_truth
    extractor = DocxExtractor(include_headers_footers=False)
    result = extractor.extract(docx_path)

    p1_block = result.blocks[1]
    assert p1_block.section_or_heading == "Security Incident Analysis"

    p2_block = result.blocks[4]
    assert p2_block.section_or_heading == "Containment Protocols"


def test_docx_empty_file(tmp_path):
    empty_file = tmp_path / "empty.docx"
    empty_file.write_bytes(b"")
    extractor = DocxExtractor()
    with pytest.raises(ValueError, match="empty"):
        extractor.extract(empty_file)
