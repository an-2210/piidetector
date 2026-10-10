"""Quality evaluation framework and structure-retention metrics for native extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.models.text_block import BlockType, ExtractionResult


@dataclass
class GroundTruthStructure:
    """Expected structural elements of a document used for structure-retention evaluation."""

    expected_paragraphs: List[str] = field(default_factory=list)
    expected_headings: List[str] = field(default_factory=list)
    expected_tables: List[List[List[str]]] = field(default_factory=list)  # list of 2D tables
    expected_slides: List[str] = field(default_factory=list)  # list of slide titles/identifiers
    expected_headers_footers: List[str] = field(default_factory=list)


@dataclass
class StructureRetentionReport:
    """Detailed score breakdown resulting from a structure retention evaluation."""

    composite_score: float
    paragraph_retention: float
    table_retention: float
    heading_retention: float
    slide_retention: float
    header_footer_retention: float
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            "composite_score": round(self.composite_score, 4),
            "percentage": f"{self.composite_score * 100:.2f}%",
            "paragraph_retention": round(self.paragraph_retention, 4),
            "table_retention": round(self.table_retention, 4),
            "heading_retention": round(self.heading_retention, 4),
            "slide_retention": round(self.slide_retention, 4),
            "header_footer_retention": round(self.header_footer_retention, 4),
            "details": self.details,
        }


class StructureRetentionEvaluator:
    """Evaluates the degree to which an ExtractionResult preserved known structural elements."""

    def __init__(
        self,
        weight_body: float = 0.35,
        weight_table: float = 0.30,
        weight_heading: float = 0.20,
        weight_slide: float = 0.15,
    ) -> None:
        self.w_body = weight_body
        self.w_table = weight_table
        self.w_heading = weight_heading
        self.w_slide = weight_slide

    def evaluate(
        self,
        result: ExtractionResult,
        ground_truth: GroundTruthStructure,
    ) -> StructureRetentionReport:
        """Calculate the structure retention metric against expected ground truth.

        Args:
            result: Actual ExtractionResult obtained from P1 pipeline.
            ground_truth: GroundTruthStructure containing known elements.

        Returns:
            StructureRetentionReport with granular component recall and composite score.
        """
        all_extracted_text = " ".join(b.text for b in result.blocks).lower()

        # 1. Paragraph Retention
        body_score = 1.0
        body_details: Dict[str, Any] = {}
        if ground_truth.expected_paragraphs:
            matched_paras = 0
            for exp_p in ground_truth.expected_paragraphs:
                # Check for substring match in extracted text
                clean_exp = exp_p.strip().lower()
                if clean_exp in all_extracted_text:
                    matched_paras += 1
                else:
                    # Partial fuzzy match: check if significant prefix/words match
                    tokens = [t for t in clean_exp.split() if len(t) > 3]
                    if tokens:
                        token_matches = sum(1 for t in tokens if t in all_extracted_text)
                        if (token_matches / len(tokens)) >= 0.7:
                            matched_paras += 1
            body_score = matched_paras / len(ground_truth.expected_paragraphs)
            body_details = {
                "expected": len(ground_truth.expected_paragraphs),
                "matched": matched_paras,
            }

        # 2. Table Retention
        table_score = 1.0
        table_details: Dict[str, Any] = {}
        if ground_truth.expected_tables:
            extracted_tables = [b for b in result.blocks if b.block_type == BlockType.TABLE.value]
            table_scores: List[float] = []

            for exp_tbl in ground_truth.expected_tables:
                exp_rows = len(exp_tbl)
                exp_cols = max(len(r) for r in exp_tbl) if exp_tbl else 0
                exp_cells = [str(c).strip().lower() for row in exp_tbl for c in row if c]

                best_tbl_match = 0.0
                for act_b in extracted_tables:
                    act_content = act_b.content or []
                    act_rows = len(act_content)
                    act_cols = max(len(r) for r in act_content) if act_content else 0

                    # Dimension retention
                    row_ratio = min(act_rows, exp_rows) / max(exp_rows, 1)
                    col_ratio = min(act_cols, exp_cols) / max(exp_cols, 1)
                    dim_score = 0.5 * row_ratio + 0.5 * col_ratio

                    # Cell content retention
                    act_text = act_b.text.lower()
                    cell_matches = sum(1 for c in exp_cells if c in act_text)
                    cell_score = (cell_matches / max(len(exp_cells), 1)) if exp_cells else 1.0

                    tbl_match = 0.4 * dim_score + 0.6 * cell_score
                    if tbl_match > best_tbl_match:
                        best_tbl_match = tbl_match

                table_scores.append(best_tbl_match)

            table_score = sum(table_scores) / len(ground_truth.expected_tables) if table_scores else 0.0
            table_details = {
                "expected_tables": len(ground_truth.expected_tables),
                "extracted_tables": len(extracted_tables),
                "per_table_scores": [round(s, 3) for s in table_scores],
            }

        # 3. Heading Retention
        heading_score = 1.0
        heading_details: Dict[str, Any] = {}
        if ground_truth.expected_headings:
            matched_headings = 0
            extracted_headings = set()
            for b in result.blocks:
                if b.section_or_heading:
                    extracted_headings.add(b.section_or_heading.strip().lower())
                if b.metadata.get("is_heading") or b.metadata.get("is_slide_title"):
                    extracted_headings.add(b.text.strip().lower())

            for exp_h in ground_truth.expected_headings:
                exp_clean = exp_h.strip().lower()
                if any(exp_clean in h or h in exp_clean for h in extracted_headings) or exp_clean in all_extracted_text:
                    matched_headings += 1

            heading_score = matched_headings / len(ground_truth.expected_headings)
            heading_details = {
                "expected": len(ground_truth.expected_headings),
                "matched": matched_headings,
            }

        # 4. Slide Retention
        slide_score = 1.0
        slide_details: Dict[str, Any] = {}
        if ground_truth.expected_slides:
            matched_slides = 0
            for exp_s in ground_truth.expected_slides:
                if exp_s.strip().lower() in all_extracted_text:
                    matched_slides += 1
            slide_score = matched_slides / len(ground_truth.expected_slides)
            slide_details = {
                "expected": len(ground_truth.expected_slides),
                "matched": matched_slides,
            }

        # 5. Header / Footer Retention
        hf_score = 1.0
        if ground_truth.expected_headers_footers:
            matched_hf = 0
            for exp_hf in ground_truth.expected_headers_footers:
                if exp_hf.strip().lower() in all_extracted_text:
                    matched_hf += 1
            hf_score = matched_hf / len(ground_truth.expected_headers_footers)

        # Dynamic normalized weighted composite score
        weights_sum = 0.0
        weighted_val = 0.0

        if ground_truth.expected_paragraphs:
            weights_sum += self.w_body
            weighted_val += self.w_body * body_score
        if ground_truth.expected_tables:
            weights_sum += self.w_table
            weighted_val += self.w_table * table_score
        if ground_truth.expected_headings:
            weights_sum += self.w_heading
            weighted_val += self.w_heading * heading_score
        if ground_truth.expected_slides:
            weights_sum += self.w_slide
            weighted_val += self.w_slide * slide_score

        composite = (weighted_val / weights_sum) if weights_sum > 0 else 1.0

        report = StructureRetentionReport(
            composite_score=composite,
            paragraph_retention=body_score,
            table_retention=table_score,
            heading_retention=heading_score,
            slide_retention=slide_score,
            header_footer_retention=hf_score,
            details={
                "paragraphs": body_details,
                "tables": table_details,
                "headings": heading_details,
                "slides": slide_details,
            },
        )

        # Record score onto result object
        result.structure_retention_score = round(composite, 4)
        return report
