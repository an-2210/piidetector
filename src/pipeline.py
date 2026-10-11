
"""Unified document extraction pipeline entry point."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Type, Union

from src.extractors.base import BaseExtractor
from src.extractors.docx_extractor import DocxExtractor
from src.extractors.pdf_extractor import PDFExtractor
from src.extractors.pptx_extractor import PptxExtractor
from src.models.text_block import ExtractionResult
from src.utils.helpers import validate_file_path

logger = logging.getLogger(__name__)

EXTRACTOR_REGISTRY: Dict[str, Type[BaseExtractor]] = {
    ".pdf": PDFExtractor,
    ".docx": DocxExtractor,
    ".pptx": PptxExtractor,
}


def get_extractor_for_file(
    file_path: Union[str, Path],
) -> BaseExtractor:
    """Resolve and instantiate the appropriate extractor.

    Args:
        file_path: Path to the target document.

    Returns:
        An instance of the appropriate BaseExtractor.

    Raises:
        ValueError: If the file format is unsupported.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    extractor_cls = EXTRACTOR_REGISTRY.get(ext)

    if not extractor_cls:
        supported = list(EXTRACTOR_REGISTRY.keys())
        raise ValueError(
            f"Unsupported document format '{ext}' for file: "
            f"{path.name}. Supported native formats are: {supported}"
        )

    return extractor_cls()


def extract_document(
    file_path: Union[str, Path],
    **options: Any,
) -> ExtractionResult:
    """Extract a document using P1, optionally followed by P2 OCR.

    By default, this function performs native extraction only, preserving
    the existing P1 behavior.

    Set enable_ocr=True to run P2 OCR after native extraction. OCR results
    are merged into the same ExtractionResult.

    OCR-specific options:
        enable_ocr: Enable the P2 OCR pipeline. Defaults to False.
        ocr_confidence_threshold: Minimum OCR confidence, from 0 to 100.
        ocr_render_dpi: DPI used when rendering PDF pages.
        ocr_upscale_factor: Image preprocessing upscale factor.

    Other options are passed to the native document extractor.

    Returns:
        ExtractionResult containing extracted TextBlocks, OCR handoff
        flags, source metadata, and any extraction errors.
    """
    # Separate P2 options so they are not accidentally passed to P1.
    extractor_options = dict(options)

    enable_ocr = extractor_options.pop("enable_ocr", False)
    ocr_confidence_threshold = extractor_options.pop(
        "ocr_confidence_threshold", 30.0
    )
    ocr_render_dpi = extractor_options.pop("ocr_render_dpi", 200)
    ocr_upscale_factor = extractor_options.pop(
        "ocr_upscale_factor", 1.5
    )

    # Validate the file path.
    try:
        path = validate_file_path(file_path)
    except Exception as exc:
        logger.error(
            "File validation failed for '%s': %s",
            file_path,
            exc,
        )
        filename = Path(file_path).name if file_path else "unknown"
        result = ExtractionResult(
            source_file=filename,
            source_type="UNKNOWN",
        )
        result.errors.append(str(exc))
        return result

    # Resolve the native extractor.
    try:
        extractor = get_extractor_for_file(path)
    except ValueError as exc:
        logger.error(
            "Unsupported file format for '%s': %s",
            path.name,
            exc,
        )
        result = ExtractionResult(
            source_file=path.name,
            source_type=path.suffix.upper().lstrip("."),
        )
        result.errors.append(str(exc))
        return result

    # Run P1 native extraction first.
    try:
        result = extractor.extract(path, **extractor_options)
    except Exception as exc:
        logger.exception(
            "Unexpected error extracting '%s'",
            path.name,
        )
        result = ExtractionResult(
            source_file=path.name,
            source_type=path.suffix.upper().lstrip("."),
        )
        result.errors.append(f"Extraction failed: {exc}")
        return result

    # Optionally run P2 OCR and merge its blocks with P1's blocks.
    if enable_ocr:
        try:
            from src.ocr.pipeline import run_ocr_pipeline

            result = run_ocr_pipeline(
                file_path=path,
                extraction_result=result,
                confidence_threshold=ocr_confidence_threshold,
                render_dpi=ocr_render_dpi,
                upscale_factor=ocr_upscale_factor,
            )
        except Exception as exc:
            logger.exception(
                "P2 OCR failed for '%s'",
                path.name,
            )
            result.errors.append(f"P2 OCR failed: {exc}")

    return result
