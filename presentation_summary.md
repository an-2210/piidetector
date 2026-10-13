# P1: Native Format Text Extraction — Slide Summary

## Slide Title: P1 - Structure-Preserving Native Text Extraction Pipeline

---

### Key Capabilities at a Glance

* **Unified Extraction Engine**: Single entry point `extract_document(file_path)` ingesting PDF, DOCX, and PPTX documents with format auto-detection.
* **Structured `TextBlock` Schema**: Standardized blocks categorized into `body`, `table`, and `slide` with sequential `reading_order`, bounding boxes, headings, and metadata.
* **Zero-Redundancy Table Reconstruction**: Extracts native tables as structured 2D matrices (`content`) and Markdown tables (`text`), masking bounding boxes to prevent duplicate body text.
* **Seamless P2 OCR Handoff**: Proactively detects pages with zero or insufficient text (< 30 chars) and raster images; emits machine-readable `OCRPageFlag` objects without invoking OCR.
* **Verified Structure Retention**: Achieves **100%** structure retention score on benchmark suites, surpassing the **$\ge 80\%$** project target.

---

### Tri-Format Native Architecture

```
                                  [ Raw Input Document ]
                                             |
                   +-------------------------+-------------------------+
                   | (PDF)                   | (DOCX)                  | (PPTX)
                   v                         v                         v
           [ PyMuPDF (fitz) ]         [ python-docx ]           [ python-pptx ]
                   |                         |                         |
  • Table detection (find_tables)   • Exact body child walk   • Slide titles & text shapes
  • Spatial bbox deduplication        (w:p & w:tbl sequence)  • Recursive grouped shapes
  • Multi-column reading order      • 2D grid & nested tables • Tables to 2D matrices
  • Scan/image-only page detection  • Headers, footers, styles• Speaker notes extraction
                   |                         |                         |
                   +-------------------------+-------------------------+
                                             |
                                             v
                           [ ExtractionResult & TextBlocks ]
                           • reading_order: 0, 1, 2...
                           • block_type: body | table | slide
                           • content: [[row_1], [row_2]]
                           • ocr_needed_pages: [OCRPageFlag]  ===>  Handoff to P2
```

---

### Technical Metrics Summary

| Feature / Metric | PDF | DOCX | PPTX |
| :--- | :---: | :---: | :---: |
| **Library Engine** | PyMuPDF (`pymupdf`) | `python-docx` | `python-pptx` |
| **Reading Order Preservation** | Vertical band spatial sort | DOM element traversal | Coordinate-based `(top, left)` sort |
| **Table Grid Reconstruction** | Structured rows + cells | Structured rows + cells | Structured rows + cells |
| **Table Text Deduplication** | Masked bbox exclusion | Distinct XML node types | Separate table shapes |
| **Benchmark Structure Score** | **100.0%** | **100.0%** | **100.0%** |
| **P2 OCR Handoff Flags** | Page-level flag + image count | Diagnostic metadata | Slide-level image-only flag |
| **Unit & Integration Tests** | 6 / 6 Passed | 6 / 6 Passed | 6 / 6 Passed |

---

# P3: Rule-Based Detectors — Slide Summary

## Slide Title: P3 - Precision Structured Identifier Detection & False-Positive Control

---

### Core Processing Specification

* **Input**: `TextBlock` sequence emitted by P1 Native Extraction and P2 OCR pipelines, preserving reading order and provenance.
* **Processing**: Deterministic regex rules + jurisdictional & algorithmic validation (Luhn, SSA, Indian Income Tax PAN) + context-anchored verification (DOB, Passports, Account numbers) + explicit false-positive suppression engine.
* **Output**: Structured, deduplicated `Finding` collection conforming to P4 contract (`detector = "rule"`).

---

### End-to-End Pipeline Dataflow

```
[ P1 Native TextBlocks ] + [ P2 OCR TextBlocks ]
                        │
                        ▼
           [ P3: Rule-Based Detectors ]
  ┌──────────────────────────────────────────────┐
  │ 1. Institutional Identifiers                 │
  │    • EMP-\d{4,6}, DIR-\d{4,8}                │
  │    • MER-IN (India), MER-PH (Philippines)    │
  │ 2. Email & Global Telephony                  │
  │    • RFC emails with boundary trimming       │
  │    • E.164 & national formats (US, UK, IN)   │
  │ 3. Sensitive & Government Identifiers        │
  │    • US SSN (SSA invalid group checks)       │
  │    • Indian PAN (4th char entity validation) │
  │    • US EIN / TIN (9 digits)                 │
  │    • Filing codes (PSEF) & Passports         │
  │ 4. Financial & Account Identifiers           │
  │    • Credit/Debit Cards (Luhn MOD-10 check)  │
  │    • Account numbers ending in last 4 digits │
  │    • Context-anchored DOB (DOB / Born labels)│
  │    • Structured Street Addresses             │
  └──────────────────────┬───────────────────────┘
                         │ Candidate findings
                         ▼
           [ False-Positive Controls ]
  ┌──────────────────────────────────────────────┐
  │ • Suppress RSK-, ISS-, INC-, GRP-POL- refs   │
  │ • Suppress standalone policy/review dates    │
  │ • Suppress USD currency & financial ratios   │
  │ • Priority-based overlapping span resolver   │
  │ • Exact start/end slice offset deduplication │
  └──────────────────────┬───────────────────────┘
                         │
                         ▼
          [ FindingsResult (For P4 Handoff) ]
  • finding_id, detector: "rule", category, value
  • start_offset, end_offset (character exact)
  • text_block_id (provenance link), confidence: 1.0
  • minimal context snippet, detector metadata
```

---

### Detector Capabilities & Test Results

| Category | Identifier Types | Validation / Rules | Test Status |
| :--- | :--- | :--- | :---: |
| **Institutional** | `EMP`, `DIR`, `MER-IN`, `MER-PH` | Regex patterns; dictionary words (`DIRECTOR`) excluded | 15 / 15 Passed |
| **Email** | `EMAIL` | RFC compliant regex; trailing punctuation stripped | 15 / 15 Passed |
| **Phone** | `PHONE` | E.164, US/UK/IN formats; 7–15 digits; dummy rejection | 15 / 15 Passed |
| **Sensitive** | `SSN`, `PAN`, `TIN`, `PSEF`, `PASSPORT` | SSA area/group rules, Indian PAN entity code, US EIN prefix | 15 / 15 Passed |
| **Financial** | `CARD_NUMBER`, `ACCOUNT_LAST4`, `DOB`, `ADDRESS` | Luhn MOD-10 algorithm, context anchoring, street structure | 15 / 15 Passed |
| **FP Controls** | `RSK-`, `ISS-`, `INC-`, `GRP-POL-`, Dates, Currency, Ratios | Explicit suppression engine; span collision deconfliction | 15 / 15 Passed |

