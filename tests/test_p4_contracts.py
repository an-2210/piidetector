"""Tests for the shared P3/P4 contract: Finding, vocabulary, ignore patterns, registry."""

import json

from src.models.text_block import TextBlock
from src.pii import registry
from src.pii.contracts import (
    DETECTORS,
    IGNORE_PATTERNS,
    NER_PREFERRED_TYPES,
    PII_TYPES,
    Finding,
    ignore_spans,
    overlaps_ignore,
    source_kind,
    validate_finding_dict,
)


def make_block(text="Contact Jane Roe at jane@example.com", **kwargs):
    defaults = dict(
        block_id="b-1",
        source_file="report.docx",
        source_type="DOCX",
        block_type="body",
        text=text,
        section_or_heading="Section 16.5",
        reading_order=3,
    )
    defaults.update(kwargs)
    return TextBlock(**defaults)


def test_finding_from_block_copies_location_and_slices_text():
    block = make_block()
    finding = Finding.from_block(block, 8, 16, "PERSON", "ner", 0.9, ["ner:spacy"])

    assert finding.text == "Jane Roe"
    assert finding.block_id == "b-1"
    assert finding.source_file == "report.docx"
    assert finding.source_type == "DOCX"
    assert finding.block_type == "body"
    assert finding.source_kind == "body"
    assert finding.section_or_heading == "Section 16.5"
    assert finding.reading_order == 3
    assert finding.identity_id is None


def test_finding_round_trips_through_json():
    block = make_block()
    finding = Finding.from_block(block, 8, 16, "PERSON", "ner", 0.9, ["ner:spacy"])

    payload = json.loads(json.dumps(finding.to_dict()))

    assert Finding.from_dict(payload) == finding
    assert validate_finding_dict(payload) == []


def test_source_kind_reports_image_ocr_provenance():
    block = make_block(metadata={"source": "image_ocr"})
    assert source_kind(block) == "image_ocr"


def test_validate_flags_bad_label_detector_and_span():
    good = Finding.from_block(make_block(), 0, 7, "PERSON", "rule", 0.9, ["rule:p3"]).to_dict()
    bad = dict(good, pii_type="NOT_A_TYPE", detector="magic", start=5, end=5)

    problems = validate_finding_dict(bad)

    assert any("pii_type" in p for p in problems)
    assert any("detector" in p for p in problems)
    assert any("span" in p for p in problems)


def test_validate_flags_missing_field():
    data = Finding.from_block(make_block(), 0, 4, "ORG", "ner", 0.5, ["ner:gliner"]).to_dict()
    del data["sources"]
    assert validate_finding_dict(data) == ["missing field 'sources'"]


def test_vocabulary_covers_required_labels():
    for label in ("PERSON", "ORG", "ADDRESS", "EMAIL", "PHONE", "EMP_ID", "DIR_ID",
                  "MER_IN_ID", "MER_PH_ID", "SSN", "PAN", "PASSPORT", "PESEL", "TIN",
                  "CARD_LAST4", "ACCOUNT_LAST4", "DOB"):
        assert label in PII_TYPES
    assert NER_PREFERRED_TYPES == {"PERSON", "ORG", "ADDRESS"}
    assert DETECTORS == ("rule", "ner")


def test_ignore_patterns_suppress_reference_ids_usd_ratios_and_policy_dates():
    text = (
        "Ref RSK-2024-0031 and ISS-77 and INC-123 and GRP-POL-9 "
        "cost $12,500 or USD 4000, ratio 3:1, effective date 01/04/2025."
    )
    spans = ignore_spans(text)
    for needle in ("RSK-2024-0031", "ISS-77", "INC-123", "GRP-POL-9", "$12,500",
                   "USD 4000", "3:1", "effective date 01/04/2025"):
        start = text.index(needle)
        assert overlaps_ignore(start, start + len(needle), spans), needle


def test_ignore_patterns_do_not_suppress_plain_names_or_emails():
    text = "Jane Roe emailed jane.roe@example.com on 12 March 2026."
    assert ignore_spans(text) == []
    assert len(IGNORE_PATTERNS) >= 7


def test_registry_returns_none_when_no_rule_detector():
    registry.clear_registered_detectors()
    findings, warnings = registry.collect_rule_findings([make_block()], include_p3=False)
    assert findings is None
    assert warnings == []


def test_registry_uses_registered_detector_and_survives_failure():
    class Good:
        def detect(self, blocks):
            return [Finding.from_block(blocks[0], 0, 4, "EMAIL", "rule", 0.95, ["rule:p3"])]

    class Broken:
        def detect(self, blocks):
            raise RuntimeError("boom")

    registry.clear_registered_detectors()
    try:
        registry.register_rule_detector(Good())
        registry.register_rule_detector(Broken())
        findings, warnings = registry.collect_rule_findings([make_block()], include_p3=False)
    finally:
        registry.clear_registered_detectors()

    assert [f.pii_type for f in findings] == ["EMAIL"]
    assert len(warnings) == 1 and "boom" in warnings[0]
