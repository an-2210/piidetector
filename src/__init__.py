"""P1: Native Format Text Extraction Package.

Provides extraction pipelines for PDF, DOCX, and PPTX documents into structured
TextBlocks, OCR handoff flags, and structure retention evaluations.
"""

from src.extractors import BaseExtractor, DocxExtractor, PDFExtractor, PptxExtractor
from src.models import (
    BlockType,
    ExtractionResult,
    OCRPageFlag,
    SourceType,
    TextBlock,
)
from src.pipeline import extract_document, get_extractor_for_file

__all__ = [
    "extract_document",
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
]
