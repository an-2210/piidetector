# P1: Native Format Text Extraction Pipeline

> **Subsystem**: P1 (Document Processing & Structured Text Extraction)  
> **Target Formats**: PDF, DOCX, PPTX  
> **Output**: Structured, serializable `TextBlock` models and `OCRPageFlag` handoff objects for P2.

---

## 1. Overview & System Boundaries

The **P1 Native Format Text Extraction** pipeline ingests raw documents in PDF, DOCX, and PPTX formats and extracts their contents into structured `TextBlock` objects categorized into `body`, `table`, and `slide`.

### Scope Boundaries
* **Included in P1**:
  * Native text layer extraction from PDF, DOCX, and PPTX.
  * Spatial reading order preservation (handling multi-column flows and interleaved tables).
  * Structured table reconstruction (2D grid rows/cells and markdown serialization).
  * Section, heading hierarchy, and speaker notes extraction.
  * Detection of missing or insufficient native text layers and generation of machine-readable OCR-needed handoff flags for **P2**.
  * Objective, ground-truth-based structure-retention evaluation framework ($\ge 80\%$ target).
* **Excluded from P1 (Strict Boundaries)**:
  * OCR engines (Tesseract, EasyOCR, PaddleOCR) — handled exclusively by **P2**.
  * Image preprocessing, deskewing, denoising, or image upscaling — handled by **P2**.
  * Text chunking, tokenization, embeddings, vector indexing — handled by **P3**.
  * CTI reporting, RAG generation, and LLM reasoning — handled by **P4**.

---

## 2. Architecture & File Layout

```text
optivcasestudy/
├── requirements.txt            # Minimal dependencies (pymupdf, python-docx, python-pptx, pillow, pytest)
├── README.md                   # Complete module documentation & integration guide
├── presentation_summary.md     # Single-slide technical executive summary
├── src/
│   ├── __init__.py             # Public API exports
│   ├── pipeline.py             # Unified entry point: extract_document()
│   ├── cli.py                  # Command-line interface
│   ├── models/
│   │   ├── __init__.py
│   │   └── text_block.py       # TextBlock, OCRPageFlag, ExtractionResult data models
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── base.py             # BaseExtractor abstract base class
│   │   ├── pdf_extractor.py    # PyMuPDF extractor (tables, spatial reading order, OCR checks)
│   │   ├── docx_extractor.py   # python-docx extractor (exact body order, tables, headers/footers)
│   │   └── pptx_extractor.py   # python-pptx extractor (titles, shapes, groups, tables, notes)
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── metrics.py          # GroundTruthStructure & StructureRetentionEvaluator
│   │   └── run_benchmark.py    # Standalone benchmark runner (verifies >= 80% score)
│   └── utils/
│       ├── __init__.py
│       └── helpers.py          # File path validation, table markdown formatting, bounding box math
└── tests/
    ├── __init__.py
    ├── conftest.py             # Programmatic fixture generators (PDF, DOCX, PPTX)
    ├── test_pdf_extractor.py   # PyMuPDF text, table, deduplication, OCR flags, corrupted files
    ├── test_docx_extractor.py  # DOCX paragraphs, interleaved tables, headers/footers, styles
    ├── test_pptx_extractor.py  # PPTX slide titles, tables, notes, grouped shapes, shapes without text
    ├── test_pipeline.py        # Unified extract_document(), error handling, JSON serialization
    ├── test_ocr_handoff.py     # OCR detection on image-only/scanned documents
    └── test_evaluation.py      # Automated validation of structure retention metrics (>= 80%)
```

---

## 3. Supported Formats & Extraction Engines

| Format | Library | Extraction Strategy & Key Features |
| :--- | :--- | :--- |
| **PDF** (`.pdf`) | PyMuPDF (`pymupdf` / `fitz`) | High-performance native vector text extraction. Extracts tables via `page.find_tables()` into rows/cols. Masks table bounding boxes to eliminate duplicate text in body blocks. Multi-column spatial sorting via vertical band grouping. Flags pages with 0 or $< 30$ characters and image presence for P2 OCR. |
| **DOCX** (`.docx`) | `python-docx` | Iterates `doc.element.body` children (`w:p` vs `w:tbl`) sequentially to preserve natural document reading order. Extracts 2D table structures and nested cell tables. Extracts section headers and footers. Propagates heading hierarchy to subsequent paragraphs. |
| **PPTX** (`.pptx`) | `python-pptx` | Extracts slide titles, text boxes, and placeholders. Recursively traverses grouped shapes (`GroupShape`). Extracts tables into structured matrices. Extracts speaker notes from `notes_slide`. Coordinates `(top, left)` sort ensures visual reading order. Flags image-only slides for P2. |

---

## 4. TextBlock & Result Data Models

### `TextBlock` Schema
Each discrete piece of content is modeled as a `TextBlock`:
```python
@dataclass
class TextBlock:
    block_id: str                      # Unique UUID
    source_file: str                   # Document filename
    source_type: str                   # "PDF", "DOCX", or "PPTX"
    block_type: str                    # "body", "table", or "slide"
    text: str                          # Extracted text (or markdown table)
    content: Optional[Any] = None      # Structured 2D table rows/cells for tables
    page_number: Optional[int] = None  # 1-indexed page (PDF)
    slide_number: Optional[int] = None # 1-indexed slide (PPTX)
    section_or_heading: Optional[str] = None # Heading or slide title context
    reading_order: int = 0             # 0-indexed sequential position
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### `OCRPageFlag` (P2 Handoff) Schema
Machine-readable metadata passed to P2:
```python
@dataclass
class OCRPageFlag:
    source_file: str                   # Document filename
    page_number: Optional[int] = None  # PDF page number
    slide_number: Optional[int] = None # PPTX slide number
    reason: str                        # "scanned_page_no_text", "insufficient_text_layer", "image_only_slide"
    char_count: int = 0                # Native characters found (if any)
    has_images: bool = False           # Whether raster images are present
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## 5. Usage & Integration Guide

### Python API

```python
from src.pipeline import extract_document

# 1. Extract any supported native document
result = extract_document("path/to/threat_report.pdf")

# 2. Access extracted blocks
for block in result.blocks:
    print(f"[{block.reading_order}] {block.block_type} (p.{block.page_number}): {block.text[:60]}")
    if block.block_type == "table":
        print(f"    Structured Grid: {len(block.content)} rows x {len(block.content[0])} cols")

# 3. Check OCR handoff flags for P2
if result.ocr_needed_pages:
    print(f"Handoff to P2: {len(result.ocr_needed_pages)} pages require OCR")
    for flag in result.ocr_needed_pages:
        print(f"  - Page {flag.page_number}: reason={flag.reason}, has_images={flag.has_images}")

# 4. Serialize for downstream modules (P3/P4)
json_payload = result.to_json(indent=2)
```

### Command-Line Interface (CLI)

```bash
# Formatted human-readable summary
python src/cli.py sample_report.docx

# Raw JSON output for pipelining into P3/P4
python src/cli.py sample_briefing.pptx --json

# Custom OCR character threshold (default: 30)
python src/cli.py scanned_document.pdf --ocr-threshold 50
```

---

## 6. Structure-Retention Evaluation Framework

The project requires a defensible metric demonstrating $\ge 80\%$ structure retention on structured documents.

### Metric Calculation

Given expected structural ground truth $E$ and extracted result $A$:

1. **Paragraph Retention ($R_{\text{body}}$)**:
   $$\text{Recall}_{\text{body}} = \frac{\sum_{p \in E_{\text{body}}} \mathbb{I}(p \text{ recovered in } A)}{|E_{\text{body}}|}$$
2. **Table Structure Retention ($R_{\text{table}}$)**:
   $$\text{Score}_{\text{table}} = 0.4 \times \left(0.5 \frac{\min(R_{\text{act}}, R_{\text{exp}})}{R_{\text{exp}}} + 0.5 \frac{\min(C_{\text{act}}, C_{\text{exp}})}{C_{\text{exp}}}\right) + 0.6 \times \text{CellRecall}$$
3. **Heading Hierarchy Retention ($R_{\text{heading}}$)**:
   $$\text{Recall}_{\text{heading}} = \frac{\sum_{h \in E_{\text{heading}}} \mathbb{I}(h \text{ captured in headings/sections})}{E_{\text{heading}}}$$
4. **Slide Content Retention ($R_{\text{slide}}$)**:
   $$\text{Recall}_{\text{slide}} = \frac{\sum_{s \in E_{\text{slide}}} \mathbb{I}(s \text{ captured in slide text})}{E_{\text{slide}}}$$

**Composite Retention Score ($S$)**:
$$S = \frac{w_b R_{\text{body}} + w_t R_{\text{table}} + w_h R_{\text{heading}} + w_s R_{\text{slide}}}{\sum w}$$
*(Weights dynamically normalize based on element types present in the document).*

### Running the Benchmark

```bash
python src/evaluation/run_benchmark.py
```

Benchmark output:
```text
================================================================================
  P1 NATIVE FORMAT EXTRACTION: STRUCTURE RETENTION BENCHMARK SUITE
================================================================================
Format   | Blocks   | Paragraphs   | Tables     | Headings   | Composite    | Status    
--------------------------------------------------------------------------------
PDF      | 5        |    100.0%   |   100.0%  |   100.0%  |    100.00%   | PASS (>=80%)
DOCX     | 7        |    100.0%   |   100.0%  |   100.0%  |    100.00%   | PASS (>=80%)
PPTX     | 5        |    100.0%   |   100.0%  |   100.0%  |    100.00%   | PASS (>=80%)
--------------------------------------------------------------------------------
Overall Average Structure Retention: 100.00% (Target: >= 80.00%)
Benchmark Result: ALL FORMATS PASSED TARGET
================================================================================
```

---

## 7. Automated Test Suite

Run all automated unit and integration tests with pytest:

```bash
pytest -v tests/
```

Results: **30 tests passed in 2.7s (100% pass rate)**.

---

## 8. Known Limitations & P3/P4 Integration Assumptions

1. **Complex PDF Multi-Column Flows**: Highly intricate magazine-style layouts with non-standard column breaks may require heuristic tuning; PyMuPDF vertical band grouping handles standard 2-column scientific and CTI reports cleanly.
2. **Merged Table Cells**: Spanning headers (colspan/rowspan) in PDFs are normalized into rectangular 2D grids with repeated or blank placeholders.
3. **P2 Handoff Contract**: Downstream module P2 consumes `result.ocr_needed_pages` to selectively perform OCR only on flagged pages, avoiding redundant compute.
4. **P3/P4 Chunking Contract**: P3 should consume `result.blocks` directly. Table blocks retain both `block.content` (for tabular embeddings) and `block.text` (markdown format for LLM context prompts).
