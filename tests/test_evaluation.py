"""Tests for structure-retention metrics and evaluation framework."""

from src.evaluation.metrics import StructureRetentionEvaluator
from src.pipeline import extract_document


def test_structure_retention_pdf(sample_pdf_with_ground_truth):
    pdf_path, ground_truth = sample_pdf_with_ground_truth
    result = extract_document(pdf_path)

    evaluator = StructureRetentionEvaluator()
    report = evaluator.evaluate(result, ground_truth)

    # Validate metric values
    assert report.composite_score >= 0.80, (
        f"PDF structure retention score {report.composite_score:.2f} must be >= 0.80 target"
    )
    assert report.paragraph_retention >= 0.80
    assert report.table_retention >= 0.80
    assert result.structure_retention_score == round(report.composite_score, 4)


def test_structure_retention_docx(sample_docx_with_ground_truth):
    docx_path, ground_truth = sample_docx_with_ground_truth
    result = extract_document(docx_path)

    evaluator = StructureRetentionEvaluator()
    report = evaluator.evaluate(result, ground_truth)

    assert report.composite_score >= 0.80, (
        f"DOCX structure retention score {report.composite_score:.2f} must be >= 0.80 target"
    )
    assert report.paragraph_retention >= 0.80
    assert report.table_retention >= 0.80
    assert report.heading_retention >= 0.80


def test_structure_retention_pptx(sample_pptx_with_ground_truth):
    pptx_path, ground_truth = sample_pptx_with_ground_truth
    result = extract_document(pptx_path)

    evaluator = StructureRetentionEvaluator()
    report = evaluator.evaluate(result, ground_truth)

    assert report.composite_score >= 0.80, (
        f"PPTX structure retention score {report.composite_score:.2f} must be >= 0.80 target"
    )
    assert report.slide_retention >= 0.80
    assert report.table_retention >= 0.80
