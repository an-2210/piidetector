"""Command-line interface for native document text extraction (P1)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.pipeline import extract_document


def main():
    parser = argparse.ArgumentParser(
        description="P1: Native Format Text Extraction CLI (PDF, DOCX, PPTX)"
    )
    parser.add_argument(
        "file_path",
        type=str,
        help="Path to the PDF, DOCX, or PPTX file to extract.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON serialization of ExtractionResult.",
    )
    parser.add_argument(
        "--ocr-threshold",
        type=int,
        default=30,
        help="Minimum character threshold for flagging PDF pages for P2 OCR (default: 30).",
    )
    args = parser.parse_args()

    result = extract_document(args.file_path, ocr_char_threshold=args.ocr_threshold)

    if args.json:
        print(result.to_json(indent=2))
        return

    print("=" * 80)
    print(f"DOCUMENT EXTRACTION SUMMARY: {result.source_file} ({result.source_type})")
    print("=" * 80)
    print(f"Total TextBlocks Extracted : {result.total_blocks}")
    print(f"Pages Needing OCR (P2)     : {len(result.ocr_needed_pages)}")
    if result.errors:
        print(f"Warnings/Errors            : {len(result.errors)}")
        for err in result.errors:
            print(f"  - {err}")
    print("-" * 80)

    if result.ocr_needed_pages:
        print("PAGES FLAGGED FOR P2 OCR HANDOFF:")
        for flag in result.ocr_needed_pages:
            loc = f"Page {flag.page_number}" if flag.page_number else f"Slide {flag.slide_number}"
            print(f"  [!] {loc}: Reason='{flag.reason}', Chars={flag.char_count}, HasImages={flag.has_images}")
        print("-" * 80)

    print("EXTRACTED TEXT BLOCKS PREVIEW:")
    for idx, block in enumerate(result.blocks[:10]):
        heading_info = f" | Section: '{block.section_or_heading}'" if block.section_or_heading else ""
        loc_info = f"p.{block.page_number}" if block.page_number else f"s.{block.slide_number}"
        print(f"[{block.reading_order:02d}] Type: {block.block_type:<6} ({loc_info}{heading_info})")
        # Print snippet
        snippet = block.text.replace("\n", " ").strip()
        if len(snippet) > 90:
            snippet = snippet[:87] + "..."
        print(f"     \"{snippet}\"")

    if result.total_blocks > 10:
        print(f"     ... ({result.total_blocks - 10} more blocks)")
    print("=" * 80)


if __name__ == "__main__":
    main()
