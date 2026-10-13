
"""Unified document extraction pipeline entry point."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Tuple, Type, Union

from src.extractors.base import BaseExtractor
from src.extractors.docx_extractor import DocxExtractor
from src.extractors.pdf_extractor import PDFExtractor
from src.extractors.pptx_extractor import PptxExtractor
from src.models.finding import Finding, FindingsResult
from src.models.text_block import (
    ExtractionResult,
    assign_deterministic_block_ids,
    document_key,
)
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

    # Deterministic block IDs: the same file gives the same IDs on every run.
    # Assigned after OCR so P2 blocks are covered too.
    assign_deterministic_block_ids(result.blocks, document_key(path))

    return result


def extract_and_detect(
    file_path: Union[str, Path],
    enable_ocr: bool = False,
    run_detectors: bool = True,
    **options: Any,
) -> Tuple[ExtractionResult, FindingsResult]:
    """Extract document text (P1 native, optional P2 OCR) and run P3 detectors.

    Args:
        file_path: Path to document (PDF, DOCX, PPTX).
        enable_ocr: Whether to run P2 OCR on flagged pages/images.
        run_detectors: Whether to run P3 rule-based sensitive identifier detectors.
        **options: Additional options forwarded to extractors or OCR pipeline.

    Returns:
        Tuple of (ExtractionResult, FindingsResult).
    """
    extraction_result = extract_document(
        file_path=file_path,
        enable_ocr=enable_ocr,
        **options,
    )

    if not run_detectors:
        empty_findings = FindingsResult(
            source_file=extraction_result.source_file,
            findings=[],
            total_findings=0,
            metadata={"status": "detectors_disabled"},
        )
        return extraction_result, empty_findings

    from src.detectors.pipeline import run_detectors_pipeline

    findings_result = run_detectors_pipeline(
        blocks=extraction_result.blocks,
        source_file=extraction_result.source_file,
    )

    return extraction_result, findings_result
