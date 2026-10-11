"""Tests for the deterministic address pattern and its fusion ranks."""


from src.pii.address import find_addresses
from src.pii.config import P4Config
from src.pii.contracts import Finding
from src.pii.fusion import fuse
from src.pii.p4 import run_p4_report
from tests.p4_support import make_block

CFG = P4Config()


def texts(text, places=()):
    return [a.text for a in find_addresses(text, list(places), CFG)]


def test_house_number_street_and_city_tail_are_one_address():
    assert texts("Reach them at 9 Broad Street, Lagos Island today.") == ["9 Broad Street, Lagos Island"]


def test_unit_prefix_and_postcode_are_included():
    assert texts("Ship to Flat 4, 12 Ozumba Mbadiwe Road, Victoria Island 101241 now.") == [
        "Flat 4, 12 Ozumba Mbadiwe Road, Victoria Island 101241"
    ]


def test_bare_city_is_never_an_address():
    assert texts("the Lagos office and Lagos Island") == []


def test_bare_street_without_number_cue_or_city_is_rejected():
    assert texts("the depot on Marina Street was closed") == []


def test_bare_street_with_city_tail_is_accepted():
    assert texts("the depot on Marina Street, Ibadan was closed") == ["Marina Street, Ibadan"]


def test_cue_makes_a_street_only_match_count():
    assert texts("Home address: Marina Street") == ["Marina Street"]


def test_confidence_rises_with_structural_signals():
    plain = find_addresses("Marina Street, Ibadan", [], CFG)[0].confidence
    house = find_addresses("14 Marina Street, Ibadan", [], CFG)[0].confidence
    cued = find_addresses("Home address: 14 Marina Street, Ibadan", [], CFG)[0].confidence
    assert plain < house < cued <= 0.95


def test_place_span_extends_a_match_to_an_adjacent_place_name():
    text = "Office: 9 Marina Street, Ibadan area"
    start = text.index("Ibadan")
    spans = find_addresses(text, [(start, start + len("Ibadan"))], CFG)
    assert [a.text for a in spans] == ["9 Marina Street, Ibadan"]


def test_disabled_pattern_emits_nothing_and_suffix_list_is_config_driven():
    assert find_addresses("14 Harbour View Road, Lagos", [], P4Config(enable_address_pattern=False)) == []
    no_road = P4Config(address_street_suffixes=("Street",))
    assert find_addresses("14 Harbour View Road, Lagos", [], no_road) == []


def test_pattern_is_deterministic():
    text = "14 Harbour View Road, Lagos and 7 Admiralty Way, Lekki"
    assert find_addresses(text, [], CFG) == find_addresses(text, [], CFG)


def _address(block, text, owner="p4", detector="ner", confidence=0.8):
    start = block.text.index(text)
    return Finding.from_block(block, start, start + len(text), "ADDRESS", detector, confidence,
                              ["p4:address_pattern"] if owner == "p4" else ["rule:p3"], owner=owner)


def _org(block, text, confidence=0.9):
    start = block.text.index(text)
    return Finding.from_block(block, start, start + len(text), "ORG", "ner", confidence, ["ner:spacy"])


def test_pattern_address_beats_overlapping_org_fragment():
    block = make_block("Depot at 9 Broad Street, Lagos Island.", block_id="b")
    address = _address(block, "9 Broad Street, Lagos Island")
    org = _org(block, "Broad Street", confidence=0.95)

    result = fuse([], [address, org], P4Config())

    assert [(f.pii_type, f.text) for f in result.kept] == [("ADDRESS", "9 Broad Street, Lagos Island")]


def test_p3_owned_address_wins_over_pattern_address():
    block = make_block("Home address: 14 Harbour View Road, Lagos", block_id="b")
    rule = _address(block, "14 Harbour View Road, Lagos", owner="p3", detector="rule", confidence=0.4)
    pattern = _address(block, "14 Harbour View Road, Lagos", owner="p4", confidence=0.9)

    result = fuse([rule], [pattern], P4Config())

    assert [f.detector for f in result.kept] == ["rule"]
    assert result.kept[0].sources == ["p4:address_pattern", "rule:p3"]  # same type: merged into the rule winner


def test_ner_address_still_fills_a_prose_gap_when_no_rule_overlaps():
    block = make_block("Mail went to Ikoyi Lagos Mainland.", block_id="b")
    gap = Finding.from_block(block, 14, 32, "ADDRESS", "ner", 0.8, ["ner:gliner"])

    result = fuse([], [gap], P4Config())

    assert [f.pii_type for f in result.kept] == ["ADDRESS"]


def test_run_p4_emits_pattern_addresses_without_any_backend():
    block = make_block("Applicant lives at 14 Harbour View Road, Lagos.", block_id="b")

    report = run_p4_report([block], None, {"defer_structured_to_rules": True}, backends=[])

    assert [(f.pii_type, f.text, f.owner) for f in report.findings] == [
        ("ADDRESS", "14 Harbour View Road, Lagos", "p4")
    ]
