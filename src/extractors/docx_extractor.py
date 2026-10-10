"""Native DOCX text and table extraction using python-docx.

Extracts paragraphs, headings, tables, headers, and footers while strictly
preserving document-level reading order and hierarchical heading relationships.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from src.extractors.base import BaseExtractor
from src.models.text_block import (
    BlockType,
    ExtractionResult,
    SourceType,
    TextBlock,
)
from src.utils.helpers import clean_text, format_table_as_markdown

logger = logging.getLogger(__name__)


class DocxExtractor(BaseExtractor):
    """Extracts native text, tables, headers, and footers from DOCX files."""

    supported_extensions = (".docx",)

    def __init__(self, include_headers_footers: bool = True) -> None:
        """Initialize DocxExtractor.

        Args:
            include_headers_footers: Whether to extract section headers and footers.
        """
        self.include_headers_footers = include_headers_footers

    def extract(
        self,
        file_path: Union[str, Path],
        include_headers_footers: Optional[bool] = None,
        **kwargs: Any,
    ) -> ExtractionResult:
        """Extract structured TextBlocks from a DOCX file.

        Args:
            file_path: Path to the .docx document.
            include_headers_footers: Override flag for header/footer extraction.

        Returns:
            ExtractionResult containing structured blocks, tables, and metadata.
        """
        path = self.validate_file(file_path)
        do_hf = include_headers_footers if include_headers_footers is not None else self.include_headers_footers

        result = ExtractionResult(
            source_file=path.name,
            source_type=SourceType.DOCX.value,
        )

        try:
            doc = docx.Document(str(path))

            # Extract core document properties
            core_props = doc.core_properties
            result.metadata = {
                "title": getattr(core_props, "title", "") or "",
                "author": getattr(core_props, "author", "") or "",
                "subject": getattr(core_props, "subject", "") or "",
                "created": str(getattr(core_props, "created", "")) or "",
                "modified": str(getattr(core_props, "modified", "")) or "",
                "section_count": len(doc.sections),
            }

            reading_order_idx = 0
            seen_hf_texts: Set[str] = set()

            # 1. Extract Headers if requested
            if do_hf:
                for sec_idx, section in enumerate(doc.sections):
                    try:
                        header = section.header
                        if header and not header.is_linked_to_previous:
                            for p in header.paragraphs:
                                text = clean_text(p.text)
                                if text and text not in seen_hf_texts:
                                    seen_hf_texts.add(text)
                                    result.blocks.append(
                                        TextBlock(
                                            source_file=path.name,
                                            source_type=SourceType.DOCX.value,
                                            block_type=BlockType.BODY.value,
                                            text=text,
                                            reading_order=reading_order_idx,
                                            metadata={
                                                "is_header": True,
                                                "section_index": sec_idx + 1,
                                                "style": p.style.name if p.style else "",
                                            },
                                        )
                                    )
                                    reading_order_idx += 1
                    except Exception as hf_err:
                        logger.debug("Non-fatal header extraction issue: %s", hf_err)

            # 2. Extract Document Body in Exact Element Sequence (interleaving paragraphs and tables)
            current_heading: Optional[str] = None

            for child in doc.element.body:
                tag = child.tag.lower()

                # Paragraph element
                if tag.endswith("p"):
                    p = Paragraph(child, doc)
                    text = clean_text(p.text)
                    if not text:
                        continue

                    style_name = p.style.name if p.style else "Normal"
                    is_heading_style = any(
                        h in style_name.lower()
                        for h in ["heading", "title", "subtitle"]
                    )

                    if is_heading_style:
                        current_heading = text

                    result.blocks.append(
                        TextBlock(
                            source_file=path.name,
                            source_type=SourceType.DOCX.value,
                            block_type=BlockType.BODY.value,
                            text=text,
                            section_or_heading=current_heading,
                            reading_order=reading_order_idx,
                            metadata={
                                "style": style_name,
                                "is_heading": is_heading_style,
                            },
                        )
                    )
                    reading_order_idx += 1

                # Table element
                elif tag.endswith("tbl"):
                    t = Table(child, doc)
                    rows_data: List[List[str]] = []

                    for row in t.rows:
                        row_cells: List[str] = []
                        for cell in row.cells:
                            # Extract clean text from all cell paragraphs
                            cell_text = "\n".join(
                                p.text.strip() for p in cell.paragraphs if p.text.strip()
                            )
                            # Handle nested tables inside cell
                            if cell.tables:
                                for nested_t in cell.tables:
                                    nested_rows = [
                                        " | ".join(c.text.strip() for c in n_row.cells)
                                        for n_row in nested_t.rows
                                    ]
                                    if nested_rows:
                                        cell_text += "\n[Nested Table:\n" + "\n".join(nested_rows) + "]"
                            row_cells.append(cell_text)
                        rows_data.append(row_cells)

                    if rows_data and any(any(c for c in row) for row in rows_data):
                        md_table = format_table_as_markdown(rows_data)
                        result.blocks.append(
                            TextBlock(
                                source_file=path.name,
                                source_type=SourceType.DOCX.value,
                                block_type=BlockType.TABLE.value,
                                text=md_table,
                                content=rows_data,
                                section_or_heading=current_heading,
                                reading_order=reading_order_idx,
                                metadata={
                                    "row_count": len(rows_data),
                                    "col_count": len(rows_data[0]) if rows_data else 0,
                                },
                            )
                        )
                        reading_order_idx += 1

            # 3. Extract Footers if requested
            if do_hf:
                for sec_idx, section in enumerate(doc.sections):
                    try:
                        footer = section.footer
                        if footer and not footer.is_linked_to_previous:
                            for p in footer.paragraphs:
                                text = clean_text(p.text)
                                if text and text not in seen_hf_texts:
                                    seen_hf_texts.add(text)
                                    result.blocks.append(
                                        TextBlock(
                                            source_file=path.name,
                                            source_type=SourceType.DOCX.value,
                                            block_type=BlockType.BODY.value,
                                            text=text,
                                            reading_order=reading_order_idx,
                                            metadata={
                                                "is_footer": True,
                                                "section_index": sec_idx + 1,
                                                "style": p.style.name if p.style else "",
                                            },
                                        )
                                    )
                                    reading_order_idx += 1
                    except Exception as f_err:
                        logger.debug("Non-fatal footer extraction issue: %s", f_err)

            result.total_blocks = len(result.blocks)

        except Exception as e:
            logger.error("DOCX extraction error for %s: %s", path.name, e)
            result.errors.append(f"DOCX extraction error: {e}")

        return result
