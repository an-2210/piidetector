"""Pytest fixtures for generating synthetic test documents (PDF, DOCX, PPTX).

Generates representative documents with known ground truth structures (headings,
paragraphs, tables, headers/footers, slides, speaker notes, and image-only pages)
without external network access or pre-existing fixture files.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Tuple

import docx
from docx.shared import Inches, Pt
from PIL import Image
import pptx
from pptx.util import Inches as PptxInches
import pymupdf
import pytest

from src.evaluation.metrics import GroundTruthStructure


@pytest.fixture
def sample_pdf_with_ground_truth(tmp_path: Path) -> Tuple[Path, GroundTruthStructure]:
    """Create a synthetic PDF with headings, paragraphs, and a vector table."""
    file_path = tmp_path / "threat_report.pdf"

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)

    # Insert Heading and Body Paragraphs
    page.insert_text((50, 50), "Threat Intelligence Briefing", fontsize=16)
    page.insert_text(
        (50, 80),
        "An advanced persistent threat campaign was detected targeting critical infrastructure.",
        fontsize=10,
    )
    page.insert_text(
        (50, 105),
        "Threat actors leveraged spear-phishing attachments to gain initial network access.",
        fontsize=10,
    )

    # Insert Table with vector borders
    table_data = [
        ["Adversary", "Target Sector", "Severity"],
        ["APT-29", "Energy Grid", "Critical"],
        ["FIN7", "Financial Services", "High"],
        ["Lazarus", "Cryptocurrency", "High"],
    ]

    rects = [
        # Row 0
        (50, 150, 180, 180), (180, 150, 350, 180), (350, 150, 500, 180),
        # Row 1
        (50, 180, 180, 210), (180, 180, 350, 210), (350, 180, 500, 210),
        # Row 2
        (50, 210, 180, 240), (180, 210, 350, 240), (350, 210, 500, 240),
        # Row 3
        (50, 240, 180, 270), (180, 240, 350, 270), (350, 240, 500, 270),
    ]

    idx = 0
    for row in table_data:
        for cell in row:
            r = rects[idx]
            page.draw_rect(pymupdf.Rect(r), color=(0, 0, 0), width=1)
            page.insert_text((r[0] + 5, r[1] + 18), cell, fontsize=9)
            idx += 1

    # Conclusion paragraph after table
    page.insert_text(
        (50, 300),
        "Recommended mitigation includes immediate credential revocation and MFA enforcement.",
        fontsize=10,
    )

    doc.save(str(file_path))
    doc.close()

    gt = GroundTruthStructure(
        expected_headings=["Threat Intelligence Briefing"],
        expected_paragraphs=[
            "An advanced persistent threat campaign was detected targeting critical infrastructure.",
            "Threat actors leveraged spear-phishing attachments to gain initial network access.",
            "Recommended mitigation includes immediate credential revocation and MFA enforcement.",
        ],
        expected_tables=[table_data],
    )

    return file_path, gt


@pytest.fixture
def multi_page_ocr_pdf(tmp_path: Path) -> Path:
    """Create a 2-page PDF where page 1 has native text and page 2 is image-only (scanned)."""
    file_path = tmp_path / "hybrid_scanned.pdf"
    doc = pymupdf.open()

    # Page 1: Normal native text
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 50), "Standard native text on page one.", fontsize=12)

    # Page 2: No text layer, only raster image
    p2 = doc.new_page(width=595, height=842)
    img = Image.new("RGB", (300, 300), color=(220, 220, 220))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    p2.insert_image(pymupdf.Rect(50, 50, 450, 450), stream=img_bytes)

    doc.save(str(file_path))
    doc.close()
    return file_path


@pytest.fixture
def sample_docx_with_ground_truth(tmp_path: Path) -> Tuple[Path, GroundTruthStructure]:
    """Create a synthetic DOCX with headers, footers, headings, interleaved tables, and body paragraphs."""
    file_path = tmp_path / "incident_response.docx"
    doc = docx.Document()

    # Header and Footer
    section = doc.sections[0]
    section.header.paragraphs[0].text = "CONFIDENTIAL - SOC INVESTIGATION"
    section.footer.paragraphs[0].text = "Incident Tracking ID: IR-2026-99"

    # Heading 1 and Paragraph 1
    doc.add_heading("Security Incident Analysis", level=1)
    doc.add_paragraph("Suspicious outbound C2 communication was observed from host 10.0.4.15.")

    # Interleaved Table
    table_data = [
        ["Timestamp", "Source IP", "Destination IP", "Action"],
        ["14:02:11", "10.0.4.15", "198.51.100.24", "Blocked"],
        ["14:03:45", "10.0.4.15", "203.0.113.88", "Terminated"],
    ]
    tbl = doc.add_table(rows=len(table_data), cols=len(table_data[0]))
    for r_idx, row in enumerate(table_data):
        for c_idx, val in enumerate(row):
            tbl.cell(r_idx, c_idx).text = val

    # Heading 2 and Paragraph 2
    doc.add_heading("Containment Protocols", level=2)
    doc.add_paragraph("Network isolation applied to infected workload. Forensic snapshot taken.")

    doc.save(str(file_path))

    gt = GroundTruthStructure(
        expected_headings=["Security Incident Analysis", "Containment Protocols"],
        expected_paragraphs=[
            "Suspicious outbound C2 communication was observed from host 10.0.4.15.",
            "Network isolation applied to infected workload. Forensic snapshot taken.",
        ],
        expected_tables=[table_data],
        expected_headers_footers=[
            "CONFIDENTIAL - SOC INVESTIGATION",
            "Incident Tracking ID: IR-2026-99",
        ],
    )

    return file_path, gt


@pytest.fixture
def sample_pptx_with_ground_truth(tmp_path: Path) -> Tuple[Path, GroundTruthStructure]:
    """Create a synthetic PPTX presentation with titles, tables, grouped shapes, and speaker notes."""
    file_path = tmp_path / "threat_briefing.pptx"
    prs = pptx.Presentation()

    # Slide 1: Title & Subtitle
    s1 = prs.slides.add_slide(prs.slide_layouts[0])
    s1.shapes.title.text = "Cyber Threat Intelligence Briefing"
    s1.placeholders[1].text = "Quarterly Strategic Review"

    # Slide 2: Title, Table, and Speaker Notes
    s2 = prs.slides.add_slide(prs.slide_layouts[5])  # Title only
    s2.shapes.title.text = "Vulnerability Prioritization"

    tbl_data = [
        ["CVE ID", "CVSS Score", "Exploited in Wild"],
        ["CVE-2026-1044", "9.8", "Yes"],
        ["CVE-2026-8812", "7.5", "No"],
    ]
    rows = len(tbl_data)
    cols = len(tbl_data[0])
    tbl_shape = s2.shapes.add_table(rows, cols, PptxInches(1), PptxInches(2), PptxInches(6), PptxInches(2))
    for r_idx, row in enumerate(tbl_data):
        for c_idx, val in enumerate(row):
            tbl_shape.table.cell(r_idx, c_idx).text = val

    s2.notes_slide.notes_text_frame.text = "Emphasize immediate patching of CVE-2026-1044."

    # Slide 3: Blank slide with Grouped Shapes
    s3 = prs.slides.add_slide(prs.slide_layouts[6])
    group = s3.shapes.add_group_shape()
    sh1 = group.shapes.add_shape(
        pptx.enum.shapes.MSO_SHAPE.RECTANGLE,
        PptxInches(1),
        PptxInches(1),
        PptxInches(3),
        PptxInches(1),
    )
    sh1.text_frame.text = "Grouped Component Alpha"
    sh2 = group.shapes.add_shape(
        pptx.enum.shapes.MSO_SHAPE.ROUNDED_RECTANGLE,
        PptxInches(1),
        PptxInches(2.5),
        PptxInches(3),
        PptxInches(1),
    )
    sh2.text_frame.text = "Grouped Component Beta"

    prs.save(str(file_path))

    gt = GroundTruthStructure(
        expected_headings=[
            "Cyber Threat Intelligence Briefing",
            "Vulnerability Prioritization",
        ],
        expected_paragraphs=[
            "Quarterly Strategic Review",
            "Grouped Component Alpha",
            "Grouped Component Beta",
            "Emphasize immediate patching of CVE-2026-1044.",
        ],
        expected_tables=[tbl_data],
        expected_slides=[
            "Cyber Threat Intelligence Briefing",
            "Vulnerability Prioritization",
        ],
    )

    return file_path, gt
