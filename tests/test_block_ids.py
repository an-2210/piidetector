"""Deterministic TextBlock IDs from extract_document (P1)."""

import shutil
import uuid

from src.models.text_block import TextBlock, deterministic_block_id
from src.pipeline import extract_document


def _ids(path):
    return [b.block_id for b in extract_document(path).blocks]


def test_same_file_gives_identical_ids_on_every_run(sample_docx_with_ground_truth):
    path, _ = sample_docx_with_ground_truth
    first, second = _ids(path), _ids(path)
    assert first and first == second


def test_ids_are_unique_within_a_document(sample_pdf_with_ground_truth):
    path, _ = sample_pdf_with_ground_truth
    ids = _ids(path)
    assert len(ids) == len(set(ids))


def test_ids_keep_the_uuid_string_format(sample_pptx_with_ground_truth):
    path, _ = sample_pptx_with_ground_truth
    for block_id in _ids(path):
        assert isinstance(block_id, str)
        assert str(uuid.UUID(block_id)) == block_id


def test_ids_depend_on_content_not_on_path(sample_docx_with_ground_truth, tmp_path):
    path, _ = sample_docx_with_ground_truth
    copy = tmp_path / "renamed_copy.docx"
    shutil.copy(path, copy)
    assert _ids(path) == _ids(copy)


def test_different_documents_get_different_ids(sample_docx_with_ground_truth, sample_pdf_with_ground_truth):
    docx_path, _ = sample_docx_with_ground_truth
    pdf_path, _ = sample_pdf_with_ground_truth
    assert not set(_ids(docx_path)) & set(_ids(pdf_path))


def test_blocks_at_different_positions_get_different_ids():
    a = TextBlock(block_type="body", page_number=1, reading_order=0)
    b = TextBlock(block_type="body", page_number=1, reading_order=1)
    assert deterministic_block_id("k", a, 0) != deterministic_block_id("k", b, 1)
