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
├── requirements.txt            # Minimal dependencies (pymupdf, python-docx, python-pptx, pillow, pytesseract, pytest)
├── README.md                   # Complete module documentation & integration guide
├── presentation_summary.md     # Single-slide technical executive summary for P1 and P3
├── src/
│   ├── __init__.py             # Public API exports (extract_document, extract_and_detect, models)
│   ├── pipeline.py             # Unified entry point: extract_document(), extract_and_detect()
│   ├── cli.py                  # Command-line interface
│   ├── models/
│   │   ├── __init__.py
│   │   ├── text_block.py       # TextBlock, OCRPageFlag, ExtractionResult data models (P1/P2)
│   │   └── finding.py          # Finding, FindingCategory, FindingsResult data models (P3 -> P4)
│   ├── extractors/             # P1 Native format extraction
│   │   ├── __init__.py
│   │   ├── base.py             # BaseExtractor abstract base class
│   │   ├── pdf_extractor.py    # PyMuPDF extractor (tables, spatial reading order, OCR checks)
│   │   ├── docx_extractor.py   # python-docx extractor (exact body order, tables, headers/footers)
│   │   └── pptx_extractor.py   # python-pptx extractor (titles, shapes, groups, tables, notes)
│   ├── ocr/                    # P2 OCR pipeline (imported from origin/main)
│   │   ├── __init__.py
│   │   ├── engine.py           # Tesseract OCR engine wrapper & adaptive segmentation
│   │   ├── image_extractor.py  # Render/extract scanned pages & embedded raster images
│   │   ├── pipeline.py         # OCR execution & duplicate text block suppression
│   │   └── preprocessing.py    # Grayscale, scaling, adaptive binarization
│   ├── detectors/              # P3 Rule-based sensitive identifier detectors
│   │   ├── __init__.py
│   │   ├── patterns.py         # Regex patterns (institutional, email, phone, sensitive, financial)
│   │   ├── validators.py       # Algorithmic validators (Luhn MOD-10, SSA SSN, Indian PAN, US TIN)
│   │   ├── filter.py           # False-positive controls (RSK-, ISS-, INC-, GRP-POL-, currency, ratios)
│   │   └── pipeline.py         # Detector engine & reading-order batch orchestrator
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
    ├── test_ocr_pipeline.py    # P2 OCR execution, Tesseract engine, scanned page recovery
    ├── test_evaluation.py      # Automated validation of structure retention metrics (>= 80%)
    └── test_detectors.py       # P3 comprehensive 15-scenario rule & false-positive test suite
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

## 7. P3: Rule-Based Detectors

The **P3 Rule-Based Detectors** module (`src/detectors/`) identifies structured sensitive identifiers from `TextBlock` streams emitted by P1 and P2, strictly enforcing false-positive suppression before emitting `Finding` records for downstream P4 consumption.

### Supported Categories & Rules

1. **Institutional Identifiers**:
   - `EMP`: `EMP-\d{4,6}` (e.g. `EMP-40123`).
   - `DIR`: `DIR-[A-Z0-9]{4,8}` or `DIR-\d{4,6}` (excluding common words `DIRECTOR`/`DIRECTION`).
   - `MER-IN`: Meridian India entity code `MER-IN-[A-Z0-9]{3,8}`.
   - `MER-PH`: Meridian Philippines entity code `MER-PH-[A-Z0-9]{3,8}`.
2. **Email Addresses**:
   - Standard RFC regex with boundary punctuation trimming (strips trailing `.`, `!`, `,`, `;`).
3. **Global Phone Numbers**:
   - E.164 and localized telephone formats (US, UK, India); requires 7–15 digits; filters dummy numbers (e.g., `000-000-0000`).
4. **Sensitive Identifiers**:
   - `SSN`: US SSA validation rules (disallows area `000`, `666`, `900–999`; group `00`; serial `0000`).
   - `PAN`: Indian Permanent Account Number with 4th character entity validation (`P`, `C`, `H`, `F`, `A`, `T`, `B`, `L`, `J`, `G`).
   - `Passport`: Context-anchored (`Passport Number: ...`) and keyword-proximate detections.
   - `PSEF`: Public Service / filing identifier `PSEF-[A-Z0-9-]{4,12}`.
   - `TIN`: US Taxpayer Identification / EIN `\d{2}-\d{7}`.
5. **Financial & Account Identifiers**:
   - `Card Numbers`: 13–19 digit cards validated with **Luhn MOD-10 algorithm**.
   - `Account Last 4`: Contextually anchored `ending in \d{4}` or `Account ****1234`.
   - `DOB`: Contextually anchored dates proximate to `Date of Birth`, `DOB`, `born`.
   - `Address`: Structural street addresses (number + street name + suffix + optional unit/city/state/zip).

### False-Positive Suppression Controls

- **Internal Reference Suppression**: Explicitly drops `RSK-`, `ISS-`, `INC-`, and `GRP-POL-` reference numbers.
- **Policy Dates**: Suppresses standalone effective dates, review dates, and governance timestamps that lack birth context.
- **Currency & Ratios**: Suppresses financial amounts (`$150,000`, `USD 50M`) and ratios/percentages (`1.5x`, `2:1`, `75%`).
- **Span Conflict Resolution**: Resolves overlapping character spans by priority (`CARD_NUMBER` > `ACCOUNT_LAST4` > digits; `SSN` > plain digits).
- **Deduplication**: Eliminates duplicate findings within identical blocks.

### Pipeline Entry Point: `extract_and_detect()`

```python
from src.pipeline import extract_and_detect

extraction_result, findings_result = extract_and_detect(
    "path/to/document.pdf",
    enable_ocr=True,      # Optional P2 OCR for scanned pages
    run_detectors=True,   # P3 rule-based detection
)

print(f"Total findings: {findings_result.total_findings}")
for finding in findings_result.findings:
    print(finding.category, finding.identifier_type, finding.value, finding.start_offset, finding.end_offset)
```

---

## 8. Automated Test Suite

Run the full automated test suite covering P1 native extraction, P2 OCR, and P3 rule-based detectors:

```bash
pytest -v tests/
```

Test coverage summary:
- **P1 Native Extraction**: 30 tests (PDF, DOCX, PPTX extraction, table reconstruction, OCR flags, benchmarks).
- **P2 OCR Pipeline**: 15 tests (Tesseract OCR execution, duplicate block deduplication, scanned PDF/DOCX/PPTX image recovery).
- **P3 Rule Detectors**: 15 tests (all 5 identifier categories, Luhn checksum, SSA rules, PAN entity checks, FP suppression, Unicode offsets, P4 contract).

**Total: 60 / 60 tests passed (100% pass rate)**.

---

## 9. P4 Redaction Handoff Contract

P3 outputs conform to the downstream P4 schema:
- `finding_id`: Unique UUID string.
- `detector`: Set to `"rule"`.
- `category`: `"institutional"`, `"email"`, `"phone"`, `"sensitive"`, `"financial"`.
- `identifier_type`: Specific tag (e.g. `"EMP"`, `"SSN"`, `"CARD_NUMBER"`, `"DOB"`).
- `value`: Target string to be redacted.
- `start_offset` & `end_offset`: Exact 0-indexed character offsets in `TextBlock.text`. Slicing `text[start_offset:end_offset]` matches `value` exactly across all Unicode codepoints.
- `text_block_id`: Foreign key reference to source `TextBlock.block_id`.
- `confidence`: Confidence score (`1.0` for deterministic rules).
- `context`: Minimal surrounding context window for audit trails.

