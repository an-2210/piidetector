"""Data models for Native Format Text Extraction (P1).

Defines structured representations of extracted text blocks, OCR handoff
flags for downstream P2 processing, and the overall extraction result container.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


# Fixed namespace for deterministic block IDs. Changing it changes every block ID.
BLOCK_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "optivcasestudy:textblock")


def document_key(file_path: Union[str, Path]) -> str:
    """SHA-256 of the file's bytes: identical content gives identical block IDs."""
    digest = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_block_id(doc_key: str, block: "TextBlock", index: int) -> str:
    """uuid5 over (document hash, page, slide, block type, reading order, list index)."""
    name = (
        f"{doc_key}|p{block.page_number}|s{block.slide_number}|"
        f"{block.block_type}|r{block.reading_order}|i{index}"
    )
    return str(uuid.uuid5(BLOCK_ID_NAMESPACE, name))


def assign_deterministic_block_ids(blocks: List["TextBlock"], doc_key: str) -> None:
    """Replace each block's ID with its deterministic uuid5, in place."""
    for index, block in enumerate(blocks):
        block.block_id = deterministic_block_id(doc_key, block, index)


class BlockType(str, Enum):
    """Categorization of extracted text blocks."""
    BODY = "body"
    TABLE = "table"
    SLIDE = "slide"


class SourceType(str, Enum):
    """Supported native document file formats."""
    PDF = "PDF"
    DOCX = "DOCX"
    PPTX = "PPTX"


@dataclass
class TextBlock:
    """Represents a discrete structural unit of text extracted from a native document.

    Attributes:
        block_id: Unique identifier for the block. Blocks returned by
            `extract_document` get a deterministic uuid5 (see
            `assign_deterministic_block_ids`). A block constructed directly
            without an ID falls back to a random uuid4.
        source_file: Original filename or path identifier.
        source_type: Format of the source document ("PDF", "DOCX", "PPTX").
        block_type: Type of block ("body", "table", "slide").
        text: Plain-text content of the block. For tables, contains serialized textual representation.
        content: Optional structured content (e.g. 2D array of rows and cells for tables).
        page_number: 1-indexed page number for page-based documents (PDF).
        slide_number: 1-indexed slide number for presentation slides (PPTX).
        section_or_heading: Contextual heading, section label, or slide title.
        reading_order: 0-indexed position preserving natural sequential reading order.
        metadata: Format-specific and structural details (bounding boxes, styles, headers/footers, etc.).
    """

    block_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_file: str = ""
    source_type: str = ""  # PDF, DOCX, PPTX
    block_type: str = BlockType.BODY.value  # body, table, slide
    text: str = ""
    content: Optional[Union[List[List[str]], Dict[str, Any], Any]] = None
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    section_or_heading: Optional[str] = None
    reading_order: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert TextBlock to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TextBlock:
        """Instantiate TextBlock from a dictionary."""
        return cls(**data)


@dataclass
class OCRPageFlag:
    """Represents a page or container lacking usable native text layer that requires P2 OCR.

    Attributes:
        page_number: 1-indexed page number (for PDF).
        slide_number: 1-indexed slide number (for PPTX, if applicable).
        source_file: Filename of the document.
        reason: Diagnostic reason for triggering OCR (e.g. "no_text_layer", "insufficient_text").
        char_count: Number of extractable text characters found (if any).
        has_images: Whether raster or bitmap images were detected on the page.
        metadata: Additional diagnostic context (e.g. image bounding boxes, dimensions).
    """

    source_file: str = ""
    page_number: Optional[int] = None
    slide_number: Optional[int] = None
    reason: str = "insufficient_text_layer"
    char_count: int = 0
    has_images: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert OCRPageFlag to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> OCRPageFlag:
        """Instantiate OCRPageFlag from a dictionary."""
        return cls(**data)


@dataclass
class ExtractionResult:
    """Top-level container for a document's extracted native contents.

    Attributes:
        source_file: Path or filename of the processed document.
        source_type: Document format ("PDF", "DOCX", "PPTX").
        total_blocks: Total number of extracted TextBlocks.
        blocks: List of structured TextBlock objects.
        ocr_needed_pages: List of OCRPageFlag items for downstream P2 handoff.
        structure_retention_score: Optional structure retention score [0.0 - 1.0].
        metadata: Global document metadata (page count, author, creation date, etc.).
        errors: Recoverable warnings or non-fatal extraction errors.
    """

    source_file: str
    source_type: str
    total_blocks: int = 0
    blocks: List[TextBlock] = field(default_factory=list)
    ocr_needed_pages: List[OCRPageFlag] = field(default_factory=list)
    structure_retention_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize complete extraction result into a dictionary."""
        return {
            "source_file": self.source_file,
            "source_type": self.source_type,
            "total_blocks": len(self.blocks),
            "blocks": [b.to_dict() for b in self.blocks],
            "ocr_needed_pages": [f.to_dict() for f in self.ocr_needed_pages],
            "structure_retention_score": self.structure_retention_score,
            "metadata": self.metadata,
            "errors": self.errors,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize complete extraction result into a JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ExtractionResult:
        """Reconstruct ExtractionResult from a dictionary."""
        blocks = [TextBlock.from_dict(b) for b in data.get("blocks", [])]
        ocr_flags = [OCRPageFlag.from_dict(f) for f in data.get("ocr_needed_pages", [])]
        return cls(
            source_file=data["source_file"],
            source_type=data["source_type"],
            total_blocks=len(blocks),
            blocks=blocks,
            ocr_needed_pages=ocr_flags,
            structure_retention_score=data.get("structure_retention_score"),
            metadata=data.get("metadata", {}),
            errors=data.get("errors", []),
        )
