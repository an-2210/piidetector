"""Tests for PyMuPDF-based PDFExtractor."""

from pathlib import Path
import pytest
from src.extractors.pdf_extractor import PDFExtractor
from src.models.text_block import BlockType, SourceType


def test_pdf_extraction_basic(sample_pdf_with_ground_truth):
    pdf_path, gt = sample_pdf_with_ground_truth
    extractor = PDFExtractor()
    result = extractor.extract(pdf_path)

    assert result.source_file == pdf_path.name
    assert result.source_type == SourceType.PDF.value
    assert result.total_blocks > 0
    assert len(result.errors) == 0

    # Verify blocks have source metadata and page numbers
    for b in result.blocks:
        assert b.source_file == pdf_path.name
        assert b.page_number == 1
        assert b.reading_order >= 0


def test_pdf_table_extraction(sample_pdf_with_ground_truth):
    pdf_path, gt = sample_pdf_with_ground_truth
    extractor = PDFExtractor()
    result = extractor.extract(pdf_path)

    table_blocks = [b for b in result.blocks if b.block_type == BlockType.TABLE.value]
    assert len(table_blocks) == 1, "Expected exactly 1 table extracted from PDF"

    tbl = table_blocks[0]
    assert tbl.content is not None
    assert len(tbl.content) == 4  # 4 rows
    assert len(tbl.content[0]) == 3  # 3 columns
    assert "Threat ID" in tbl.text or "Adversary" in tbl.text
    assert "APT-29" in tbl.text


def test_pdf_table_deduplication(sample_pdf_with_ground_truth):
    """Verify that table cell contents are NOT duplicated as body text blocks."""
    pdf_path, gt = sample_pdf_with_ground_truth
    extractor = PDFExtractor()
    result = extractor.extract(pdf_path)

    body_blocks = [b for b in result.blocks if b.block_type == BlockType.BODY.value]
    body_texts = [b.text for b in body_blocks]

    # "Energy Grid" is a cell in the table; it should not appear as its own standalone body block
    for bt in body_texts:
        assert bt.strip() != "Energy Grid"
        assert bt.strip() != "Cryptocurrency"


def test_pdf_ocr_flag_detection(multi_page_ocr_pdf):
    """Verify that image-only page without text is flagged for P2 OCR handoff."""
    extractor = PDFExtractor(ocr_char_threshold=30)
    result = extractor.extract(multi_page_ocr_pdf)

    assert len(result.ocr_needed_pages) == 1
    flag = result.ocr_needed_pages[0]
    assert flag.page_number == 2
    assert flag.has_images is True
    assert flag.reason == "scanned_page_no_text"
    assert flag.char_count == 0


def test_pdf_corrupted_file(tmp_path):
    bad_pdf = tmp_path / "corrupted.pdf"
    bad_pdf.write_bytes(b"%PDF-1.4 header followed by complete junk binary data 12345")
    extractor = PDFExtractor()
    result = extractor.extract(bad_pdf)

    assert len(result.errors) > 0
    assert any("Corrupted" in e or "error" in e.lower() for e in result.errors)


def test_pdf_empty_file(tmp_path):
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_bytes(b"")
    extractor = PDFExtractor()
    with pytest.raises(ValueError, match="empty"):
        extractor.extract(empty_pdf)
