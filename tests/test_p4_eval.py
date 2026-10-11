"""Tests for the evaluation harness: ground-truth loading, matching rules and scoring."""

from pathlib import Path

import pytest

from eval.ground_truth import GroundTruthError, GTLabel, load_ground_truth
from eval.metrics import (
    Prediction,
    build_predictions,
    identity_scores,
    match,
    normalize_text,
    prf,
    span_iou,
)
from src.pii.contracts import Finding
from tests.p4_support import make_block

SAMPLE_GT = Path(__file__).resolve().parent.parent / "eval" / "samples" / "ground_truth.json"


def label(text, pii_type="PERSON", page=None, file="a.docx", span=None, identity=None, kind="body"):
    return GTLabel(file=file, page=page, source_kind=kind, text=text, pii_type=pii_type, identity=identity, span=span)


def pred(text, pii_type="PERSON", block_id="x", start=0, file="a.docx", identity_id=None, confidence=0.9):
    finding = Finding(
        block_id=block_id, start=start, end=start + len(text), text=text, pii_type=pii_type,
        detector="ner", confidence=confidence, sources=["ner:spacy"], identity_id=identity_id,
        source_file=file, source_kind="body", block_type="body",
    )
    return Prediction(finding=finding, file=file, location=None, norm=normalize_text(text), span=None)


def test_normalize_drops_honorifics_and_punctuation():
    assert normalize_text("Dr. Priya Raman") == "priya raman"
    assert normalize_text("M. T. Achebe") == "m t achebe"
    assert normalize_text("  Globex   Ltd ") == "globex ltd"


def test_span_iou():
    assert span_iou((0, 10), (0, 10)) == 1.0
    assert span_iou((0, 10), (5, 15)) == pytest.approx(5 / 15)
    assert span_iou((0, 4), (10, 14)) == 0.0


def test_matching_ignores_block_id():
    truth = [label("Michael T. Achebe")]
    predictions = [pred("Michael T. Achebe", block_id="a-random-uuid-from-another-run")]

    result = match(truth, predictions)

    assert len(result.pairs) == 1 and not result.missed and not result.unmatched


def test_matching_requires_same_pii_type_and_file():
    assert match([label("Globex Ltd", "ORG")], [pred("Globex Ltd", "PERSON")]).pairs == []
    assert match([label("Globex Ltd", "ORG")], [pred("Globex Ltd", "ORG", file="b.docx")]).pairs == []


def test_matching_is_one_to_one():
    truth = [label("Grace Achebe"), label("Grace Achebe")]
    predictions = [pred("Grace Achebe")]

    result = match(truth, predictions)

    assert len(result.pairs) == 1
    assert len(result.missed) == 1


def test_span_labels_need_overlap_not_just_text():
    truth = [label("Michael T. Achebe", span=(100, 117))]
    far = pred("Michael T. Achebe", start=0)
    near = pred("Michael T. Achebe", start=0)
    far.span = (0, 17)
    near.span = (101, 118)

    assert match(truth, [far]).pairs == []
    assert len(match(truth, [near]).pairs) == 1


def test_prf_handles_empty_denominators():
    assert prf(0, 0, 0) == {"tp": 0, "fp": 0, "fn": 0, "precision": None, "recall": None, "f1": None}
    assert prf(2, 2, 2)["f1"] == pytest.approx(0.5)


def test_identity_scores_pairwise():
    truth = [
        label("Michael T. Achebe", identity="A"),
        label("M. T. Achebe", identity="A"),
        label("Grace Achebe", identity="C"),
    ]
    predictions = [
        pred("Michael T. Achebe", identity_id="PERSON_1"),
        pred("M. T. Achebe", identity_id="PERSON_1"),
        pred("Grace Achebe", identity_id="PERSON_1"),  # wrongly merged with A
    ]
    result = match(truth, predictions)

    scores = identity_scores(result, predictions)

    assert scores["truth_pairs"] == 1
    assert scores["linked_truth_pairs"] == 1
    assert scores["pred_pairs"] == 3
    assert scores["correct_pred_pairs"] == 1
    assert scores["precision"] == pytest.approx(1 / 3)
    assert scores["recall"] == 1.0


def test_build_predictions_maps_spans_into_document_coordinates():
    first = make_block("Alpha line.", block_id="p1", reading_order=0, source_file="d.docx")
    second = make_block("Beta Ltd here.", block_id="p2", reading_order=1, source_file="d.docx")
    finding = Finding.from_block(second, 5, 8, "ORG", "ner", 0.9, ["ner:spacy"])

    [prediction] = build_predictions([finding], [second, first])

    assert prediction.span == (len("Alpha line.") + 1 + 5, len("Alpha line.") + 1 + 8)


def test_sample_ground_truth_loads_and_has_all_source_kinds():
    truth = load_ground_truth(SAMPLE_GT)

    assert len(truth.labels) >= 30
    assert {l.source_kind for l in truth.labels} == {"body", "table", "slide", "image_ocr"}
    assert {l.pii_type for l in truth.labels} >= {"PERSON", "ORG", "ADDRESS", "EMAIL", "EMP_ID"}
    assert any(l.span is not None for l in truth.labels)
    assert {d.kind for d in truth.decoys} >= {"rsk_ref", "usd_amount", "policy_date"}


def _write(tmp_path, labels, decoys=()):
    import json

    path = tmp_path / "gt.json"
    path.write_text(json.dumps({"schema_version": 1, "labels": labels, "decoys": list(decoys)}))
    return path


GOOD = {"file": "a.docx", "page": None, "source_kind": "body", "text": "Jane Roe", "pii_type": "PERSON"}


@pytest.mark.parametrize(
    "bad, message",
    [
        ({**GOOD, "pii_type": "NOT_A_TYPE"}, "pii_type"),
        ({**GOOD, "source_kind": "footer"}, "source_kind"),
        ({**GOOD, "text": "  "}, "text"),
        ({**GOOD, "identity": "A", "pii_type": "EMAIL"}, "identity"),
        ({**GOOD, "span": [5, 2]}, "span"),
        ({**GOOD, "page": 0}, "page"),
        ({k: v for k, v in GOOD.items() if k != "file"}, "file"),
        ({**GOOD, "extra": 1}, "unknown"),
    ],
)
def test_loader_rejects_schema_violations(tmp_path, bad, message):
    with pytest.raises(GroundTruthError, match=message):
        load_ground_truth(_write(tmp_path, [bad]))


def test_ner_only_mode_runs_end_to_end_when_models_installed():
    pytest.importorskip("presidio_analyzer")
    spacy = pytest.importorskip("spacy")
    try:
        spacy.load("en_core_web_lg")
    except OSError:
        pytest.skip("en_core_web_lg not installed")
    from eval.run_eval import run_mode

    truth = load_ground_truth(SAMPLE_GT)
    outcome = run_mode("ner_only", truth, SAMPLE_GT.parent)

    assert outcome["status"] == "ran"
    assert outcome["backends"] == ["spacy"]
    assert outcome["scores"]["overall"]["tp"] > 0
    # Known, measured false positive: spaCy tags "the Risk Committee" as ORG.
    assert [h["decoy"] for h in outcome["scores"]["decoy_hits"]] == ["Risk Committee"]
