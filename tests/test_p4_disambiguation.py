"""Tests for person vs organisation disambiguation and prose-focus weighting."""

from src.pii.config import P4Config
from src.pii.disambiguate import decide_label
from src.pii.prose import block_weight, in_priority_section, is_id_like
from tests.p4_support import make_block


def decide(block_text, span, label, backend_labels=None, config=None):
    start = block_text.index(span)
    return decide_label(
        span,
        label,
        block_text,
        start,
        start + len(span),
        backend_labels or {label},
        config or P4Config(),
    )


def test_org_suffix_relabels_person_to_org_without_penalty():
    d = decide("Payments were sent to Globex Ltd last week.", "Globex Ltd", "PERSON")
    assert (d.label, d.penalty, d.reason) == ("ORG", 1.0, "strong_cue_relabel")


def test_person_title_relabels_org_to_person():
    d = decide("Mr Okafor signed the form.", "Mr Okafor", "ORG")
    assert d.label == "PERSON"
    assert d.reason == "strong_cue_relabel"


def test_title_before_span_counts_as_person_cue():
    d = decide("Dr. Priya Raman reviewed it.", "Priya Raman", "ORG")
    assert d.label == "PERSON"


def test_weak_org_context_conflicting_with_person_is_ambiguous():
    # "vendor" hints at an organisation, the model says PERSON: keep the label, lower confidence.
    text = "Logs came from the vendor Quinlan Partners yesterday."
    d = decide(text, "Quinlan Partners", "PERSON")
    assert d.label == "PERSON"
    assert d.penalty == P4Config().ambiguity_penalty
    assert d.reason == "weak_cue_conflict"


def test_backend_disagreement_without_cues_is_penalised_not_guessed():
    d = decide("Adaeze reviewed the logs.", "Adaeze", "PERSON", backend_labels={"PERSON", "ORG"})
    assert d.label == "PERSON"
    assert d.penalty == P4Config().ambiguity_penalty
    assert d.reason == "backend_disagreement"


def test_agreeing_person_with_person_cue_has_no_penalty():
    d = decide("The analyst Tomas Reyes escalated it.", "Tomas Reyes", "PERSON")
    assert (d.label, d.penalty) == ("PERSON", 1.0)


def test_non_person_labels_pass_through_unchanged():
    d = decide("Reach them at jane@example.com", "jane@example.com", "EMAIL")
    assert (d.label, d.penalty, d.reason) == ("EMAIL", 1.0, "not_person_or_org")


def test_block_weight_prefers_prose_over_tables_and_ocr():
    config = P4Config()
    body = make_block("x", block_type="body")
    table = make_block("x", block_type="table")
    ocr = make_block("x", block_type="body", metadata={"source": "image_ocr"})

    assert block_weight(body, config) == 1.0
    assert block_weight(table, config) == config.block_weights["table"]
    assert block_weight(ocr, config) == config.block_weights["image_ocr"]
    assert block_weight(table, config) < block_weight(body, config)
    assert block_weight(ocr, config) < block_weight(body, config)


def test_id_like_tokens_are_detected_but_names_are_not():
    assert is_id_like("EMP-40123")
    assert is_id_like("RSK-2024-0031")
    assert not is_id_like("Michael T. Achebe")
    assert not is_id_like("Globex")


def test_priority_section_matches_case_document_sections():
    config = P4Config()
    assert in_priority_section(make_block("x", section_or_heading="16.5 Insider Activity"), config)
    assert in_priority_section(make_block("x", section_or_heading="§16.8 Exposure"), config)
    assert not in_priority_section(make_block("x", section_or_heading="3.1 Scope"), config)
    assert not in_priority_section(make_block("x", section_or_heading=None), config)
