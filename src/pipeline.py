"""Unified document extraction pipeline entry point."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Type, Union

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


def get_extractor_for_file(file_path: Union[str, Path]) -> BaseExtractor:
    """Resolve and instantiate the appropriate extractor for the given file extension.

    Args:
        file_path: Path to the target document.

    Returns:
        An instance of BaseExtractor.

    Raises:
        ValueError: If file format extension is unsupported.
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    extractor_cls = EXTRACTOR_REGISTRY.get(ext)
    if not extractor_cls:
        supported = list(EXTRACTOR_REGISTRY.keys())
        raise ValueError(
            f"Unsupported document format '{ext}' for file: {path.name}. "
            f"Supported native formats are: {supported}"
        )
    return extractor_cls()


def extract_document(
    file_path: Union[str, Path],
    **options: Any,
) -> ExtractionResult:
    """Primary entry point to extract structured TextBlocks from PDF, DOCX, or PPTX.

    Args:
        file_path: Path to raw PDF, DOCX, or PPTX file.
        **options: Format-specific configuration passed directly to extractor
                   (e.g. ocr_char_threshold, include_headers_footers, include_speaker_notes).

    Returns:
        ExtractionResult containing structured TextBlocks, OCR handoff flags,
        and source metadata.
    """
    try:
        path = validate_file_path(file_path)
    except Exception as e:
        logger.error("File validation failed for '%s': %s", file_path, e)
        filename = Path(file_path).name if file_path else "unknown"
        res = ExtractionResult(source_file=filename, source_type="UNKNOWN")
        res.errors.append(str(e))
        return res

    try:
        extractor = get_extractor_for_file(path)
    except ValueError as val_err:
        logger.error("Unsupported file format for '%s': %s", path.name, val_err)
        res = ExtractionResult(
            source_file=path.name,
            source_type=path.suffix.upper().lstrip("."),
        )
        res.errors.append(str(val_err))
        return res

    try:
        return extractor.extract(path, **options)
    except Exception as exc:
        logger.error("Unexpected error extracting '%s': %s", path.name, exc)
        res = ExtractionResult(
            source_file=path.name,
            source_type=path.suffix.upper().lstrip("."),
        )
        res.errors.append(f"Extraction failed: {exc}")
        return res
