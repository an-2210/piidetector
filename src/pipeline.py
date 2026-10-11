
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
    """Resolve the appropriate native extractor."""
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
    """Extract document content using P1, optionally followed by P2 OCR.

    OCR is disabled by default to preserve existing P1 behavior.

    OCR options:
        enable_ocr: Enable P2 OCR. Defaults to False.
        ocr_confidence_threshold: Minimum OCR confidence (0-100).
        ocr_render_dpi: DPI for rendering PDF pages.
        ocr_upscale_factor: Image preprocessing scale factor.

    Remaining options are passed to the native extractor.
    """
    extractor_options = dict(options)

    enable_ocr = extractor_options.pop("enable_ocr", False)
    confidence_threshold = extractor_options.pop(
        "ocr_confidence_threshold", 30.0
    )
    render_dpi = extractor_options.pop("ocr_render_dpi", 200)
    upscale_factor = extractor_options.pop("ocr_upscale_factor", 1.5)

    try:
        path = validate_file_path(file_path)
    except Exception as exc:
        logger.error("File validation failed for '%s': %s", file_path, exc)
        filename = Path(file_path).name if file_path else "unknown"
        result = ExtractionResult(
            source_file=filename,
            source_type="UNKNOWN",
        )
        result.errors.append(str(exc))
        return result

    try:
        extractor = get_extractor_for_file(path)
    except ValueError as exc:
        logger.error(
            "Unsupported file format for '%s': %s", path.name, exc
        )
        result = ExtractionResult(
            source_file=path.name,
            source_type=path.suffix.upper().lstrip("."),
        )
        result.errors.append(str(exc))
        return result

    try:
        result = extractor.extract(path, **extractor_options)
    except Exception as exc:
        logger.exception("Unexpected error extracting '%s'", path.name)
        result = ExtractionResult(
            source_file=path.name,
            source_type=path.suffix.upper().lstrip("."),
        )
        result.errors.append(f"Extraction failed: {exc}")
        return result

    if enable_ocr:
        try:
            from src.ocr.pipeline import run_ocr_pipeline

            result = run_ocr_pipeline(
                file_path=path,
                extraction_result=result,
                confidence_threshold=confidence_threshold,
                render_dpi=render_dpi,
                upscale_factor=upscale_factor,
            )
        except Exception as exc:
            logger.exception("P2 OCR failed for '%s'", path.name)
            result.errors.append(f"P2 OCR failed: {exc}")

    return result
