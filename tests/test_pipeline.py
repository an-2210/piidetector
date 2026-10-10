"""Tests for unified extract_document pipeline and serialization."""

import json
from pathlib import Path
import pytest
from src.models.text_block import ExtractionResult, TextBlock
from src.pipeline import extract_document, get_extractor_for_file


def test_unified_pipeline_pdf(sample_pdf_with_ground_truth):
    pdf_path, _ = sample_pdf_with_ground_truth
    result = extract_document(pdf_path)
    assert result.source_type == "PDF"
    assert result.total_blocks > 0
    assert len(result.errors) == 0


def test_unified_pipeline_docx(sample_docx_with_ground_truth):
    docx_path, _ = sample_docx_with_ground_truth
    result = extract_document(docx_path)
    assert result.source_type == "DOCX"
    assert result.total_blocks > 0
    assert len(result.errors) == 0


def test_unified_pipeline_pptx(sample_pptx_with_ground_truth):
    pptx_path, _ = sample_pptx_with_ground_truth
    result = extract_document(pptx_path)
    assert result.source_type == "PPTX"
    assert result.total_blocks > 0
    assert len(result.errors) == 0


def test_unified_pipeline_unsupported_format(tmp_path):
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("plain text")
    result = extract_document(txt_file)
    assert len(result.errors) > 0
    assert "Unsupported" in result.errors[0]


def test_unified_pipeline_missing_file():
    result = extract_document("non_existent_file_12345.pdf")
    assert len(result.errors) > 0
    assert "not found" in result.errors[0].lower()


def test_text_block_serialization(sample_pdf_with_ground_truth):
    pdf_path, _ = sample_pdf_with_ground_truth
    result = extract_document(pdf_path)

    # Convert to dict and JSON
    res_dict = result.to_dict()
    assert isinstance(res_dict, dict)
    assert "blocks" in res_dict
    assert "ocr_needed_pages" in res_dict

    res_json = result.to_json()
    assert isinstance(res_json, str)

    # Reconstruct from dict
    restored = ExtractionResult.from_dict(res_dict)
    assert restored.source_file == result.source_file
    assert restored.total_blocks == result.total_blocks
    assert len(restored.blocks) == len(result.blocks)
    assert restored.blocks[0].text == result.blocks[0].text
