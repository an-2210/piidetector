"""Fusion outcomes for deliberate rule/NER conflicts, and NER+mock versus NER-only."""

from src.pii import registry
from src.pii.config import P4Config
from src.pii.contracts import Finding
from src.pii.fusion import fuse
from src.pipeline import extract_document
from eval.mock_p3 import MockRegexP3
from tests.p4_support import make_block

CFG = P4Config()
STRUCTURED_SAMPLE = "eval/samples/structured_conflicts.docx"


def span(block, text, pii_type, detector, confidence, sources, owner=None):
    start = block.text.index(text)
    return Finding.from_block(block, start, start + len(text), pii_type, detector, confidence, sources, owner=owner)


def test_unowned_rule_person_and_ner_person_on_same_span_keep_the_ner_winner():
    block = make_block("Michael T. Achebe reviewed it.", block_id="b")
    rule = span(block, "Michael T. Achebe", "PERSON", "rule", 0.7, ["rule:p3"])
    ner = span(block, "Michael T. Achebe", "PERSON", "ner", 0.85, ["ner:spacy"])

    [kept] = fuse([rule], [ner], CFG).kept

    assert kept.detector == "ner"
    assert kept.sources == ["ner:spacy", "rule:p3"]  # agreement is recorded


def test_labelled_p3_person_beats_ner_org_on_the_same_span():
    # spaCy tags "Grace Achebe" as ORG in a table. The labelled field is authoritative.
    block = make_block("Applicant: Grace Achebe, Head of Audit.", block_id="b")
    labelled = span(block, "Grace Achebe", "PERSON", "rule", 0.99, ["rule:mock_p3:labelled_name"], owner="p3")
    ner_org = span(block, "Grace Achebe", "ORG", "ner", 0.9, ["ner:spacy"])

    result = fuse([labelled], [ner_org], CFG).kept

    assert [(f.pii_type, f.detector) for f in result] == [("PERSON", "rule")]


def test_labelled_p3_address_beats_an_overlapping_ner_address_fragment():
    block = make_block("Home address: 9 Marina Road, Ikoyi.", block_id="b")
    labelled = span(block, "9 Marina Road, Ikoyi", "ADDRESS", "rule", 0.99, ["rule:mock_p3:labelled_address"], owner="p3")
    fragment = span(block, "Ikoyi", "ADDRESS", "ner", 0.9, ["ner:gliner"])

    result = fuse([labelled], [fragment], CFG).kept

    assert [(f.text, f.detector) for f in result] == [("9 Marina Road, Ikoyi", "rule")]


def test_exact_duplicate_email_from_two_patterns_becomes_one_finding():
    block = make_block("Email: priya.raman@globex-ltd.com", block_id="b")
    general = span(block, "priya.raman@globex-ltd.com", "EMAIL", "rule", 0.99, ["rule:mock_p3:email"], owner="p3")
    labelled = span(block, "priya.raman@globex-ltd.com", "EMAIL", "rule", 0.99, ["rule:mock_p3:labelled_email"], owner="p3")

    result = fuse([general, labelled], [], CFG).kept

    assert len(result) == 1
    assert result[0].sources == ["rule:mock_p3:email", "rule:mock_p3:labelled_email"]


def test_structured_rule_beats_an_overlapping_ner_org_fragment():
    block = make_block("SSN: 123-45-6789 is on file.", block_id="b")
    ssn = span(block, "123-45-6789", "SSN", "rule", 0.99, ["rule:mock_p3:ssn"], owner="p3")
    ner_org = span(block, "SSN: 123-45-6789", "ORG", "ner", 0.9, ["ner:spacy"])

    result = fuse([ssn], [ner_org], CFG).kept

    assert [(f.pii_type, f.text) for f in result] == [("SSN", "123-45-6789")]


def _types(findings):
    return {f.pii_type for f in findings}


def test_ner_plus_mock_differs_from_ner_only_on_structured_identifiers():
    registry.clear_registered_detectors()
    ner_only = extract_document(STRUCTURED_SAMPLE, enable_ner=True, ner_config={"defer_structured_to_rules": False})

    registry.register_rule_detector(MockRegexP3())
    try:
        with_mock = extract_document(STRUCTURED_SAMPLE, enable_ner=True, ner_config={"defer_structured_to_rules": True})
    finally:
        registry.clear_registered_detectors()

    mock_findings = with_mock.metadata["p4"]["findings"]
    ner_findings = ner_only.metadata["p4"]["findings"]
    mock_types = {f["pii_type"] for f in mock_findings}
    ner_types = {f["pii_type"] for f in ner_findings}

    for pii_type in ("SSN", "PAN", "PESEL", "TIN", "DOB", "CARD_LAST4", "ACCOUNT_LAST4", "DIR_ID", "MER_IN_ID", "MER_PH_ID"):
        assert pii_type in mock_types, pii_type
    assert mock_types - ner_types  # the mock adds types NER-only never emits

    labelled = [f for f in mock_findings if f["text"] == "Michael T. Achebe"]
    assert labelled and labelled[0]["detector"] == "rule"
