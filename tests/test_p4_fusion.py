"""Tests for rule/NER fusion: overlap resolution, merging, confidence and threshold."""

import random

from src.pii.config import P4Config
from src.pii.contracts import Finding
from src.pii.fusion import fuse
from tests.p4_support import load_mock_p3, make_block

BLOCK = make_block(
    "Michael T. Achebe emailed michael.achebe@acme-corp.com today.",
    block_id="b1",
    reading_order=1,
)
EMAIL_START = BLOCK.text.index("michael.achebe")
EMAIL_END = EMAIL_START + len("michael.achebe@acme-corp.com")


def finding(start, end, pii_type, detector, confidence=0.8, sources=None, block=BLOCK):
    return Finding.from_block(
        block, start, end, pii_type, detector, confidence,
        sources or [f"{detector}:test"],
    )


def cfg(**kw):
    return P4Config(**kw)


def test_structured_rule_beats_overlapping_ner_span():
    # NER proposes "achebe" inside the email; the rule's EMAIL span must win.
    rule = finding(EMAIL_START, EMAIL_END, "EMAIL", "rule", 0.99, ["rule:p3"])
    ner_inside = finding(EMAIL_START + 8, EMAIL_START + 14, "PERSON", "ner", 0.9, ["ner:spacy"])

    result = fuse([rule], [ner_inside], cfg())

    assert [(f.pii_type, f.detector) for f in result.kept] == [("EMAIL", "rule")]
    assert result.absorbed == 1


def test_ner_beats_rule_for_person_and_unions_sources():
    rule = finding(0, 17, "PERSON", "rule", 0.7, ["rule:p3"])  # "Michael T. Achebe"
    ner = finding(0, 17, "PERSON", "ner", 0.85, ["ner:spacy"])

    result = fuse([rule], [ner], cfg())

    assert len(result.kept) == 1
    winner = result.kept[0]
    assert winner.detector == "ner"
    assert winner.sources == ["ner:spacy", "rule:p3"]


def test_exact_duplicate_rule_findings_merge_with_union_of_sources():
    a = finding(0, 17, "PERSON", "rule", 0.7, ["rule:p3"])
    b = finding(0, 17, "PERSON", "rule", 0.7, ["rule:p3b"])

    result = fuse([a, b], [], cfg())

    assert len(result.kept) == 1
    assert result.kept[0].sources == ["rule:p3", "rule:p3b"]


def test_rule_confidence_is_fixed_high():
    rule = finding(EMAIL_START, EMAIL_END, "EMAIL", "rule", 0.12, ["rule:p3"])
    result = fuse([rule], [], cfg(rule_confidence=0.95))
    assert result.kept[0].confidence == 0.95


def test_multi_source_agreement_boosts_confidence():
    a = finding(0, 17, "PERSON", "ner", 0.80, ["ner:spacy"])
    b = finding(0, 17, "PERSON", "ner", 0.78, ["ner:gliner"])

    result = fuse([], [a, b], cfg(agreement_boost=0.05))

    assert len(result.kept) == 1
    assert result.kept[0].sources == ["ner:gliner", "ner:spacy"]
    assert result.kept[0].confidence == 0.85


def test_below_threshold_goes_to_debug_list_only():
    weak = finding(0, 17, "PERSON", "ner", 0.3, ["ner:gliner"])

    result = fuse([], [weak], cfg(confidence_threshold=0.5))

    assert result.kept == []
    assert [f.text for f in result.below_threshold] == ["Michael T. Achebe"]


def test_different_type_overlap_keeps_longer_span_deterministically():
    org = finding(0, 14, "ORG", "ner", 0.9, ["ner:gliner"])
    person = finding(0, 7, "PERSON", "ner", 0.9, ["ner:spacy"])

    result = fuse([], [org, person], cfg())

    assert [(f.pii_type, f.text) for f in result.kept] == [("ORG", "Michael T. Ach")]


def test_output_is_independent_of_input_order():
    rule = [
        finding(0, 17, "PERSON", "rule", 0.7, ["rule:p3"]),
        finding(EMAIL_START, EMAIL_END, "EMAIL", "rule", 0.99, ["rule:p3"]),
    ]
    ner = [
        finding(0, 17, "PERSON", "ner", 0.85, ["ner:spacy"]),
        finding(EMAIL_START + 8, EMAIL_START + 14, "PERSON", "ner", 0.9, ["ner:spacy"]),
    ]
    baseline = [f.to_dict() for f in fuse(rule, ner, cfg()).kept]

    rng = random.Random(7)
    for _ in range(5):
        shuffled_rule = rule[:]
        shuffled_ner = ner[:]
        rng.shuffle(shuffled_rule)
        rng.shuffle(shuffled_ner)
        assert [f.to_dict() for f in fuse(shuffled_rule, shuffled_ner, cfg()).kept] == baseline


def test_fixture_fusion_keeps_structured_rules_and_person_spans():
    blocks, mock_rules = load_mock_p3()
    ner = [
        # NER finds the same person as P3 in the prose block, with a longer name.
        Finding.from_block(blocks[0], 0, 17, "PERSON", "ner", 0.9, ["ner:spacy"]),
    ]

    result = fuse(mock_rules, ner, cfg())

    kept_types = sorted(f.pii_type for f in result.kept)
    assert kept_types.count("EMAIL") == 2  # one per block
    assert kept_types.count("EMP_ID") == 2
    assert kept_types.count("PERSON") == 4  # Achebe (merged), roster, Raman, slide
    merged = [f for f in result.kept if f.block_id == "casefile:body_165" and f.pii_type == "PERSON"]
    assert merged[0].detector == "ner" and "rule:p3" in merged[0].sources
