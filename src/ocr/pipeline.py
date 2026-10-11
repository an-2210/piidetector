
"""P2 OCR pipeline and merge with P1 extraction results."""

from __future__ import annotations

from pathlib import Path
import re

from src.models.text_block import ExtractionResult, TextBlock
from src.ocr.engine import recognize_text
from src.ocr.image_extractor import extract_image_items
from src.ocr.preprocessing import preprocess_image


def _normalize(text: str) -> str:
    """Normalize whitespace and punctuation for exact duplicate checking."""
    return re.sub(r"\W+", "", text.casefold())


def _is_duplicate(
    text: str,
    page_number: int | None,
    slide_number: int | None,
    existing_blocks: list[TextBlock],
) -> bool:
    """Check for exact normalized duplicates in the same document location.

    Conservative exact matching prevents distinct identifiers that differ
    by one or more characters from being discarded.
    """
    normalized = _normalize(text)

    if not normalized:
        return True

    for block in existing_blocks:
        if (
            block.page_number != page_number
            or block.slide_number != slide_number
        ):
            continue

        candidate = _normalize(block.text)

        if candidate and normalized == candidate:
            return True

    return False


def run_ocr_pipeline(
    file_path: str | Path,
    extraction_result: ExtractionResult,
    confidence_threshold: float = 30.0,
    render_dpi: int = 200,
    upscale_factor: float = 1.5,
) -> ExtractionResult:
    """Extract image text and merge it into the P1 extraction result.

    Native P1 blocks are retained. OCR detections are added as body blocks
    with image_ocr provenance and image-coordinate bounding boxes.
    """
    path = Path(file_path)

    items = extract_image_items(
        path,
        extraction_result=extraction_result,
        render_dpi=render_dpi,
    )

    result = extraction_result
    merged_blocks = list(result.blocks)

    next_order = max(
        (block.reading_order for block in merged_blocks),
        default=-1,
    ) + 1

    pages_with_ocr: set[int] = set()
    slides_with_ocr: set[int] = set()
    failures: list[str] = []
    blocks_added = 0

    for item in items:
        try:
            prepared = preprocess_image(
                item.image,
                upscale_factor=upscale_factor,
            )

            detections = recognize_text(
                prepared,
                confidence_threshold=confidence_threshold,
            )
        except Exception as exc:
            location = (
                f"page {item.page_number}"
                if item.page_number is not None
                else f"slide {item.slide_number}"
                if item.slide_number is not None
                else "unknown location"
            )
            failures.append(f"{location}: {exc}")
            continue

        scale = upscale_factor if upscale_factor > 0 else 1.0

        for detection in detections:
            text = detection.get("text", "").strip()

            if not text:
                continue

            page_number = item.page_number
            slide_number = item.slide_number

            if _is_duplicate(
                text,
                page_number,
                slide_number,
                merged_blocks,
            ):
                continue

            bbox = [
                round(float(coordinate) / scale, 2)
                for coordinate in detection["bbox"]
            ]

            block = TextBlock(
                source_file=result.source_file,
                source_type=result.source_type,
                block_type="body",
                text=text,
                page_number=page_number,
                slide_number=slide_number,
                reading_order=next_order,
                metadata={
                    "source": "image_ocr",
                    "ocr_engine": "tesseract",
                    "confidence": float(detection["confidence"]),
                    "bbox": bbox,
                    "bbox_coordinate_space": "image_pixels",
                    "image_kind": item.metadata.get("kind"),
                    "image_metadata": item.metadata,
                },
            )

            merged_blocks.append(block)
            next_order += 1
            blocks_added += 1

            if page_number is not None:
                pages_with_ocr.add(page_number)

            if slide_number is not None:
                slides_with_ocr.add(slide_number)

    result.blocks = merged_blocks
    result.total_blocks = len(merged_blocks)

    result.metadata["p2_ocr"] = {
        "engine": "tesseract",
        "images_processed": len(items),
        "ocr_blocks_added": blocks_added,
        "pages_with_new_ocr_blocks": sorted(pages_with_ocr),
        "slides_with_new_ocr_blocks": sorted(slides_with_ocr),
        "failures": failures,
    }

    result.errors.extend(
        f"P2 OCR warning: {failure}" for failure in failures
    )

    return result
