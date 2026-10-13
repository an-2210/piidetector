"""Unified Document Extraction & Rule-Based Detection Package (P1, P2, P3).

Provides extraction pipelines for PDF, DOCX, and PPTX documents into structured
TextBlocks, P2 OCR pipeline, and P3 rule-based sensitive identifier detectors.
"""

from src.detectors import (
    FalsePositiveFilter,
    RuleBasedDetector,
    run_detectors_pipeline,
)
from src.extractors import BaseExtractor, DocxExtractor, PDFExtractor, PptxExtractor
from src.models import (
    BlockType,
    ExtractionResult,
    Finding,
    FindingCategory,
    FindingsResult,
    OCRPageFlag,
    SourceType,
    TextBlock,
)
from src.pipeline import (
    extract_and_detect,
    extract_document,
    get_extractor_for_file,
)

__all__ = [
    "extract_document",
    "extract_and_detect",
    "get_extractor_for_file",
    "TextBlock",
    "OCRPageFlag",
    "ExtractionResult",
    "BlockType",
    "SourceType",
    "BaseExtractor",
    "PDFExtractor",
    "DocxExtractor",
    "PptxExtractor",
    "Finding",
    "FindingCategory",
    "FindingsResult",
    "RuleBasedDetector",
    "run_detectors_pipeline",
    "FalsePositiveFilter",
]

