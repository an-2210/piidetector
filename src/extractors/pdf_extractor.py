"""Native PDF text and table extraction using PyMuPDF (pymupdf).

Extracts text blocks, reconstructs tables as structured grids, preserves
reading order, prevents table text duplication, and flags pages requiring OCR for P2.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pymupdf

from src.extractors.base import BaseExtractor
from src.models.text_block import (
    BlockType,
    ExtractionResult,
    OCRPageFlag,
    SourceType,
    TextBlock,
)
from src.utils.helpers import clean_text, format_table_as_markdown, rect_overlaps_bbox

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """Extracts native text, tables, and structure from PDF documents using PyMuPDF."""

    supported_extensions = (".pdf",)

    def __init__(self, ocr_char_threshold: int = 30) -> None:
        """Initialize PDFExtractor.

        Args:
            ocr_char_threshold: Minimum character count below which a page is
                                flagged as needing OCR handoff to P2.
        """
        self.ocr_char_threshold = ocr_char_threshold

    def extract(
        self,
        file_path: Union[str, Path],
        ocr_char_threshold: Optional[int] = None,
        **kwargs: Any,
    ) -> ExtractionResult:
        """Extract structured TextBlocks from a native PDF document.

        Args:
            file_path: Path to the PDF file.
            ocr_char_threshold: Optional override for the OCR trigger threshold.

        Returns:
            ExtractionResult containing structured blocks, OCR flags, and metadata.
        """
        path = self.validate_file(file_path)
        threshold = ocr_char_threshold if ocr_char_threshold is not None else self.ocr_char_threshold

        result = ExtractionResult(
            source_file=path.name,
            source_type=SourceType.PDF.value,
        )

        doc = None
        try:
            doc = pymupdf.open(str(path))

            # Handle password protection / encryption
            if doc.is_encrypted:
                auth_success = doc.authenticate("")  # Try default empty password
                if not auth_success:
                    result.errors.append(f"PDF is encrypted with password protection: {path.name}")
                    return result

            # Extract document-level metadata
            result.metadata = {
                "page_count": len(doc),
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "subject": doc.metadata.get("subject", ""),
                "creator": doc.metadata.get("creator", ""),
                "producer": doc.metadata.get("producer", ""),
                "format_version": getattr(doc, "pdf_version", ""),
            }

            if len(doc) == 0:
                result.errors.append("PDF contains 0 pages.")
                return result

            reading_order_idx = 0

            for page_idx in range(len(doc)):
                page = doc[page_idx]
                page_num = page_idx + 1

                # 1. Inspect page text and check for OCR handoff
                raw_page_text = page.get_text()
                clean_page_text = clean_text(raw_page_text)
                char_count = len(clean_page_text)

                # Count images on the page
                image_list = page.get_images(full=True)
                has_images = len(image_list) > 0

                # OCR Evaluation Check
                if char_count == 0:
                    reason = "scanned_page_no_text" if has_images else "empty_page_no_text"
                    result.ocr_needed_pages.append(
                        OCRPageFlag(
                            source_file=path.name,
                            page_number=page_num,
                            reason=reason,
                            char_count=0,
                            has_images=has_images,
                            metadata={"image_count": len(image_list)},
                        )
                    )
                elif char_count < threshold:
                    result.ocr_needed_pages.append(
                        OCRPageFlag(
                            source_file=path.name,
                            page_number=page_num,
                            reason="insufficient_text_layer",
                            char_count=char_count,
                            has_images=has_images,
                            metadata={"image_count": len(image_list), "sample": clean_page_text[:50]},
                        )
                    )

                # 2. Extract tables
                table_blocks_on_page: List[Tuple[Tuple[float, float, float, float], TextBlock]] = []
                table_bboxes: List[Tuple[float, float, float, float]] = []

                try:
                    tables = page.find_tables()
                    for tab in tables:
                        extracted_table = tab.extract()
                        if not extracted_table or not any(row for row in extracted_table):
                            continue

                        # Clean cell values
                        cleaned_rows = [
                            [str(cell).strip() if cell is not None else "" for cell in row]
                            for row in extracted_table
                        ]

                        table_bbox = tuple(float(c) for c in tab.bbox)
                        table_bboxes.append(table_bbox)

                        markdown_text = format_table_as_markdown(cleaned_rows)
                        tbl_block = TextBlock(
                            source_file=path.name,
                            source_type=SourceType.PDF.value,
                            block_type=BlockType.TABLE.value,
                            text=markdown_text,
                            content=cleaned_rows,
                            page_number=page_num,
                            reading_order=0,  # assigned during spatial sort below
                            metadata={
                                "bbox": table_bbox,
                                "row_count": len(cleaned_rows),
                                "col_count": len(cleaned_rows[0]) if cleaned_rows else 0,
                            },
                        )
                        table_blocks_on_page.append((table_bbox, tbl_block))
                except Exception as tbl_err:
                    logger.warning("Table detection error on page %d: %s", page_num, tbl_err)
                    result.errors.append(f"Page {page_num} table detection warning: {tbl_err}")

                # 3. Extract text blocks and filter out table bounding boxes to prevent duplicates
                # get_text("blocks") returns (x0, y0, x1, y1, "text", block_no, block_type)
                # block_type 0 = text, 1 = image
                body_blocks_on_page: List[Tuple[Tuple[float, float, float, float], TextBlock]] = []
                page_blocks = page.get_text("blocks")

                for blk in page_blocks:
                    x0, y0, x1, y1, b_text, b_no, b_type = blk
                    if b_type != 0:
                        continue  # Skip image blocks

                    block_text = clean_text(b_text)
                    if not block_text:
                        continue

                    blk_bbox = (float(x0), float(y0), float(x1), float(y1))

                    # Deduplication: check if block falls inside any detected table
                    is_inside_table = False
                    for t_bbox in table_bboxes:
                        if rect_overlaps_bbox(blk_bbox, t_bbox, threshold=0.4):
                            is_inside_table = True
                            break

                    if is_inside_table:
                        continue  # Avoid duplicating table content as body text

                    # Detect simple heading heuristics based on length and newlines
                    lines = block_text.splitlines()
                    possible_heading = None
                    if len(lines) == 1 and len(block_text) < 100:
                        possible_heading = block_text

                    text_block = TextBlock(
                        source_file=path.name,
                        source_type=SourceType.PDF.value,
                        block_type=BlockType.BODY.value,
                        text=block_text,
                        page_number=page_num,
                        section_or_heading=possible_heading,
                        reading_order=0,
                        metadata={
                            "bbox": blk_bbox,
                            "block_number": b_no,
                        },
                    )
                    body_blocks_on_page.append((blk_bbox, text_block))

                # 4. Determine reading order on the page
                # Sort all blocks on this page by visual reading order:
                # Grouping by vertical bands and horizontal alignment handles multi-column layouts
                all_page_items = table_blocks_on_page + body_blocks_on_page
                # Sort primarily by y0 (top-to-bottom), secondary x0 (left-to-right)
                all_page_items.sort(key=lambda item: (round(item[0][1] / 8) * 8, item[0][0]))

                for _, item_block in all_page_items:
                    item_block.reading_order = reading_order_idx
                    reading_order_idx += 1
                    result.blocks.append(item_block)

            result.total_blocks = len(result.blocks)

        except pymupdf.FileDataError as fde:
            result.errors.append(f"Corrupted or invalid PDF file: {fde}")
        except Exception as e:
            result.errors.append(f"PDF extraction error: {e}")
        finally:
            if doc is not None:
                doc.close()

        return result
