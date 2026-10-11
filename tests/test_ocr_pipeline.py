
"""Tests for the P2 OCR pipeline and duplicate detection."""

from src.models.text_block import BlockType, SourceType, TextBlock
from src.ocr.pipeline import _is_duplicate


def make_text_block(
    text: str,
    page_number: int = 1,
    slide_number: int | None = None,
) -> TextBlock:
    """Create a native text block for testing duplicate detection."""
    return TextBlock(
        block_id=f"test-block-{page_number}",
        source_file="test.pdf",
        source_type=SourceType.PDF,
        block_type=BlockType.BODY,
        text=text,
        content={},
        page_number=page_number,
        slide_number=slide_number,
        section_or_heading=None,
        reading_order=0,
        metadata={"source": "native"},
    )


def test_ocr_pipeline_detects_duplicate_native_text():
    """OCR text identical to native text should be considered a duplicate."""
    existing_blocks = [
        make_text_block("Employee ID EMP-40123")
    ]

    assert _is_duplicate(
        "Employee ID EMP-40123",
        1,
        None,
        existing_blocks,
    )


def test_ocr_pipeline_detects_punctuation_variations():
    """Punctuation and capitalization differences should not create duplicates."""
    existing_blocks = [
        make_text_block("Employee ID: EMP-40123!")
    ]

    assert _is_duplicate(
        "employee id emp-40123",
        1,
        None,
        existing_blocks,
    )


def test_ocr_pipeline_allows_same_text_on_different_pages():
    """Identical text on different pages should not be treated as a duplicate."""
    existing_blocks = [
        make_text_block("Account Status: Active", page_number=1)
    ]

    assert not _is_duplicate(
        "Account Status: Active",
        2,
        None,
        existing_blocks,
    )


def test_ocr_pipeline_rejects_empty_text():
    """Empty or punctuation-only OCR text should be rejected."""
    existing_blocks = [
        make_text_block("Employee ID EMP-40123")
    ]

    assert _is_duplicate("", 1, None, existing_blocks)
    assert _is_duplicate("!!!", 1, None, existing_blocks)


def test_ocr_pipeline_allows_different_identifiers():
    """Different identifiers should not be treated as duplicates."""
    existing_blocks = [
        make_text_block("Employee ID EMP-40123")
    ]

    assert not _is_duplicate(
        "Employee ID EMP-40124",
        1,
        None,
        existing_blocks,
    )


def test_ocr_pipeline_allows_shared_prefix_identifiers():
    """Identifiers sharing a prefix but having different values are distinct."""
    existing_blocks = [
        make_text_block("Account Number ACC-12345")
    ]

    assert not _is_duplicate(
        "Account Number ACC-12346",
        1,
        None,
        existing_blocks,
    )


def test_ocr_pipeline_recovers_scanned_pdf_text(multi_page_ocr_pdf):
    """P2 should recover text from the scanned second page of a PDF."""
    from src.pipeline import extract_document
    from src.ocr.pipeline import run_ocr_pipeline

    # P1 extracts native text and identifies the scanned page.
    result = extract_document(multi_page_ocr_pdf)
    original_block_count = len(result.blocks)

    assert any(
        flag.page_number == 2
        for flag in result.ocr_needed_pages
    ), "P1 should flag the scanned second page."

    # P2 runs OCR and merges the recovered text with P1's results.
    result = run_ocr_pipeline(multi_page_ocr_pdf, result)

    ocr_blocks = [
        block
        for block in result.blocks
        if block.metadata.get("source") == "image_ocr"
    ]

    assert len(result.blocks) >= original_block_count
    assert ocr_blocks, "P2 should recover text from the scanned page."

    assert all(
        block.page_number == 2
        for block in ocr_blocks
    ), "OCR blocks should belong to the scanned second page."

    recovered_text = " ".join(
        block.text for block in ocr_blocks
    ).casefold()

    assert "emp-40123" in recovered_text, (
        f"Employee ID was not recovered. OCR text: {recovered_text}"
    )

    assert "account status" in recovered_text, (
        f"Account status was not recovered. OCR text: {recovered_text}"
    )

    assert result.metadata["p2_ocr"]["images_processed"] > 0
    assert result.metadata["p2_ocr"]["ocr_blocks_added"] > 0

def test_main_pipeline_runs_ocr_when_enabled(multi_page_ocr_pdf):
    """The main pipeline should invoke P2 when enable_ocr=True."""
    from src.pipeline import extract_document

    result = extract_document(
        multi_page_ocr_pdf,
        enable_ocr=True,
    )

    ocr_blocks = [
        block
        for block in result.blocks
        if block.metadata.get("source") == "image_ocr"
    ]

    assert ocr_blocks, "The main pipeline should return OCR text."
    assert any(
        "emp-40123" in block.text.casefold()
        for block in ocr_blocks
    ), "The OCR result should contain the expected employee ID."

    assert "p2_ocr" in result.metadata
    assert result.metadata["p2_ocr"]["ocr_blocks_added"] > 0

def test_main_pipeline_recovers_text_from_docx_image(docx_with_ocr_image):
    """The main pipeline should OCR images embedded in DOCX documents."""
    from src.pipeline import extract_document

    result = extract_document(
        docx_with_ocr_image,
        enable_ocr=True,
    )

    ocr_blocks = [
        block
        for block in result.blocks
        if block.metadata.get("source") == "image_ocr"
    ]

    assert ocr_blocks, "OCR should recover text from the DOCX image."

    recovered_text = " ".join(
        block.text for block in ocr_blocks
    ).casefold()

    assert "emp-40123" in recovered_text, (
        f"Employee ID was not recovered. OCR text: {recovered_text}"
    )
    assert "account status" in recovered_text, (
        f"Account status was not recovered. OCR text: {recovered_text}"
    )

    assert result.metadata["p2_ocr"]["images_processed"] > 0
    assert result.metadata["p2_ocr"]["ocr_blocks_added"] > 0


def test_main_pipeline_recovers_text_from_pptx_image(pptx_with_ocr_image):
    """The main pipeline should OCR images embedded in PPTX slides."""
    from src.pipeline import extract_document

    result = extract_document(
        pptx_with_ocr_image,
        enable_ocr=True,
    )

    ocr_blocks = [
        block
        for block in result.blocks
        if block.metadata.get("source") == "image_ocr"
    ]

    assert ocr_blocks, "OCR should recover text from the PPTX image."

    recovered_text = " ".join(
        block.text for block in ocr_blocks
    ).casefold()

    assert "acc-12345" in recovered_text, (
        f"Account number was not recovered. OCR text: {recovered_text}"
    )
    assert "account status" in recovered_text, (
        f"Account status was not recovered. OCR text: {recovered_text}"
    )

    assert all(
        block.slide_number == 1
        for block in ocr_blocks
    ), "OCR blocks should be associated with slide 1."

    assert result.metadata["p2_ocr"]["images_processed"] > 0
    assert result.metadata["p2_ocr"]["ocr_blocks_added"] > 0

def test_ocr_engine_returns_empty_for_blank_image():
    """A blank image should not produce recognized text."""
    from PIL import Image
    from src.ocr.engine import recognize_text

    image = Image.new("RGB", (800, 400), color="white")

    detections = recognize_text(image)

    assert isinstance(detections, list)
    assert all(
        detection["text"].strip()
        for detection in detections
    )


def test_ocr_engine_handles_grayscale_image():
    """The OCR engine should accept grayscale images."""
    from PIL import Image, ImageDraw, ImageFont
    from src.ocr.engine import recognize_text

    image = Image.new("L", (1200, 300), color=255)
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except OSError:
        font = ImageFont.load_default(size=64)

    draw.text(
        (30, 70),
        "Employee ID: EMP-40123",
        fill=0,
        font=font,
    )

    detections = recognize_text(image)
    recovered_text = " ".join(
        item["text"] for item in detections
    ).casefold()

    assert "emp-40123" in recovered_text, (
        f"Expected employee ID in OCR output: {recovered_text}"
    )


def test_preprocessing_handles_blank_image():
    """Preprocessing a blank image should return a valid grayscale image."""
    from PIL import Image
    from src.ocr.preprocessing import preprocess_image

    image = Image.new("RGB", (400, 200), color="white")

    processed = preprocess_image(image)

    assert processed.mode == "L"
    assert processed.size[0] > 0
    assert processed.size[1] > 0


def test_preprocessing_rejects_no_valid_dimensions():
    """Preprocessing should fail clearly for an empty image."""
    import pytest
    from PIL import Image
    from src.ocr.preprocessing import preprocess_image

    image = Image.new("RGB", (0, 0))

    with pytest.raises((ValueError, RuntimeError)):
        preprocess_image(image)

def test_ocr_pipeline_continues_after_one_image_fails(
    multi_page_ocr_pdf,
    monkeypatch,
):
    """A failed image should not prevent OCR on subsequent images."""
    from PIL import Image

    from src.pipeline import extract_document
    from src.ocr.image_extractor import ImageItem
    import src.ocr.pipeline as ocr_pipeline

    result = extract_document(multi_page_ocr_pdf)

    # Simulate two images from the same document.
    first_image = Image.new("RGB", (200, 100), color="white")
    second_image = Image.new("RGB", (200, 100), color="white")

    items = [
        ImageItem(
            source_file=multi_page_ocr_pdf.name,
            source_type="PDF",
            image=first_image,
            page_number=1,
            metadata={"kind": "test_image", "test_id": 1},
        ),
        ImageItem(
            source_file=multi_page_ocr_pdf.name,
            source_type="PDF",
            image=second_image,
            page_number=2,
            metadata={"kind": "test_image", "test_id": 2},
        ),
    ]

    monkeypatch.setattr(
        ocr_pipeline,
        "extract_image_items",
        lambda *args, **kwargs: items,
    )

    # Keep preprocessing deterministic for this test.
    monkeypatch.setattr(
        ocr_pipeline,
        "preprocess_image",
        lambda image, **kwargs: image,
    )

    calls = {"count": 0}

    def fake_recognize_text(image, **kwargs):
        calls["count"] += 1

        if calls["count"] == 1:
            raise RuntimeError("Simulated OCR failure")

        return [
            {
                "text": "Account Status: Active",
                "confidence": 0.95,
                "bbox": [10, 10, 180, 40],
            }
        ]

    monkeypatch.setattr(
        ocr_pipeline,
        "recognize_text",
        fake_recognize_text,
    )

    result = ocr_pipeline.run_ocr_pipeline(
        multi_page_ocr_pdf,
        result,
    )

    # OCR should attempt both images despite the first failure.
    assert calls["count"] == 2

    # The second image should still produce an OCR block.
    recovered_blocks = [
        block
        for block in result.blocks
        if block.metadata.get("source") == "image_ocr"
    ]

    assert any(
        block.text == "Account Status: Active"
        and block.page_number == 2
        for block in recovered_blocks
    )

    # The failure should be recorded rather than silently discarded.
    assert any(
        "Simulated OCR failure" in error
        for error in result.errors
    )

    assert result.metadata["p2_ocr"]["ocr_blocks_added"] == 1
    assert len(result.metadata["p2_ocr"]["failures"]) == 1
