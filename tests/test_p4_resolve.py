"""Tests for entity resolution: initials, email matching, co-occurrence and no over-merge."""

import random

from src.pii.contracts import Finding
from src.pii.linking import extract_evidence
from src.pii.resolve import email_matches_name, names_compatible, parse_name, resolve_identities
from tests.p4_support import load_mock_p3, make_block


def person(block, text, start=None):
    start = block.text.index(text) if start is None else start
    return Finding.from_block(block, start, start + len(text), "PERSON", "ner", 0.9, ["ner:spacy"])


def evidence(block, text, pii_type):
    start = block.text.index(text)
    return Finding.from_block(block, start, start + len(text), pii_type, "rule", 0.99, ["rule:p3"])


def identity_of(result, text):
    matches = {f.identity_id for f in result.findings if f.text == text and f.pii_type == "PERSON"}
    assert len(matches) == 1, (text, matches)
    return matches.pop()


def test_initials_match_full_name():
    block = make_block("Michael T. Achebe reported it. Later M. T. Achebe confirmed.", block_id="b1")
    findings = [person(block, "Michael T. Achebe"), person(block, "M. T. Achebe")]

    result = resolve_identities(findings, [], [block])

    assert identity_of(result, "Michael T. Achebe") == identity_of(result, "M. T. Achebe")


def test_email_links_to_name_when_unambiguous():
    prose = make_block("Michael Achebe reported it.", block_id="b1", reading_order=1)
    other = make_block("Contact michael.achebe@acme-corp.com for follow-up.", block_id="b2", reading_order=2)
    findings = [person(prose, "Michael Achebe")]
    emails = [evidence(other, "michael.achebe@acme-corp.com", "EMAIL")]

    result = resolve_identities(findings, emails, [prose, other])

    assert result.findings[0].identity_id == "PERSON_1"
    assert result.identities[0]["linked_evidence"] == ["EMAIL:michael.achebe@acme-corp.com"]


def test_no_merge_on_shared_surname_alone():
    block = make_block("Michael Achebe and Mary Achebe both attended.", block_id="b1")
    findings = [person(block, "Michael Achebe"), person(block, "Mary Achebe")]

    result = resolve_identities(findings, [], [block])

    assert identity_of(result, "Michael Achebe") != identity_of(result, "Mary Achebe")
    assert len(result.identities) == 2


def test_ambiguous_initial_does_not_merge_into_either_person():
    block = make_block("Michael Achebe, Mark Achebe and M. Achebe were there.", block_id="b1")
    findings = [person(block, "Michael Achebe"), person(block, "Mark Achebe"), person(block, "M. Achebe")]

    result = resolve_identities(findings, [], [block])

    initial = identity_of(result, "M. Achebe")
    assert initial not in {identity_of(result, "Michael Achebe"), identity_of(result, "Mark Achebe")}


def test_email_with_only_surname_does_not_link():
    prose = make_block("Michael Achebe reported it.", block_id="b1", reading_order=1)
    other = make_block("Send to achebe@acme-corp.com", block_id="b2", reading_order=2)
    result = resolve_identities(
        [person(prose, "Michael Achebe")],
        [evidence(other, "achebe@acme-corp.com", "EMAIL")],
        [prose, other],
    )
    assert result.identities[0]["linked_evidence"] == []


def test_emp_id_cooccurring_in_table_row_links_the_row_person():
    table = make_block(
        "| Name | Employee |\n| --- | --- |\n| M. T. Achebe | EMP-40123 |\n| Priya Raman | EMP-77001 |",
        block_id="t1",
        block_type="table",
        content=[["Name", "Employee"], ["M. T. Achebe", "EMP-40123"], ["Priya Raman", "EMP-77001"]],
    )
    prose = make_block("Michael T. Achebe raised the alert.", block_id="p1", reading_order=5)
    findings = [person(table, "M. T. Achebe"), person(table, "Priya Raman"), person(prose, "Michael T. Achebe")]
    evidence_findings = [
        evidence(table, "EMP-40123", "EMP_ID"),
        evidence(table, "EMP-77001", "EMP_ID"),
    ]

    result = resolve_identities(findings, evidence_findings, [table, prose])

    assert identity_of(result, "M. T. Achebe") == identity_of(result, "Michael T. Achebe")
    assert identity_of(result, "Priya Raman") != identity_of(result, "M. T. Achebe")


def test_id_seen_with_two_different_people_is_a_conflict_not_a_merge():
    block_a = make_block("Alice Carter filed EMP-55555 on Monday.", block_id="a", reading_order=1)
    block_b = make_block("Brian Dowd also cited EMP-55555 on Tuesday.", block_id="b", reading_order=2)
    findings = [person(block_a, "Alice Carter"), person(block_b, "Brian Dowd")]
    ids = [evidence(block_a, "EMP-55555", "EMP_ID"), evidence(block_b, "EMP-55555", "EMP_ID")]

    result = resolve_identities(findings, ids, [block_a, block_b])

    # Each block has one name, but one ID tied to two people is bad data: never merge on it.
    assert identity_of(result, "Alice Carter") != identity_of(result, "Brian Dowd")
    assert len(result.conflicts) == 1
    assert "EMP_ID EMP-55555" in result.conflicts[0]


def test_id_in_one_scope_with_two_people_is_left_unlinked():
    block = make_block("Alice Carter and Brian Dowd both cite EMP-55555.", block_id="a")
    findings = [person(block, "Alice Carter"), person(block, "Brian Dowd")]
    ids = [evidence(block, "EMP-55555", "EMP_ID")]

    result = resolve_identities(findings, ids, [block])

    assert identity_of(result, "Alice Carter") != identity_of(result, "Brian Dowd")


def test_identity_ids_are_stable_under_input_reordering():
    b1 = make_block("Zed Quinn and Michael Achebe met.", block_id="b1", reading_order=1)
    b2 = make_block("M. T. Achebe later. Anna Berg too.", block_id="b2", reading_order=2)
    findings = [
        person(b1, "Zed Quinn"),
        person(b1, "Michael Achebe"),
        person(b2, "M. T. Achebe"),
        person(b2, "Anna Berg"),
    ]
    blocks = [b1, b2]

    baseline = [(f.text, f.identity_id) for f in resolve_identities(findings, [], blocks).findings]
    rng = random.Random(3)
    for _ in range(5):
        shuffled = findings[:]
        rng.shuffle(shuffled)
        out = {f.text: f.identity_id for f in resolve_identities(shuffled, [], blocks).findings}
        assert [(t, out[t]) for t, _ in baseline] == baseline


def test_parse_name_and_compatibility_helpers():
    assert parse_name("Dr. Priya Raman") is not None
    assert parse_name("Achebe") is None
    assert names_compatible(parse_name("M. T. Achebe"), parse_name("Michael T. Achebe"))
    assert not names_compatible(parse_name("Michael Achebe"), parse_name("Mary Achebe"))
    assert not names_compatible(parse_name("Michael T. Achebe"), parse_name("Michael O. Achebe"))
    assert email_matches_name("m.achebe", parse_name("M. Achebe"))
    assert not email_matches_name("marcus.achebe", parse_name("Michael Achebe"))


def test_extract_evidence_finds_emails_and_emp_ids_in_block_order():
    block = make_block("Mail jane.doe@example.com about EMP-40123.", block_id="x")
    found = extract_evidence([block])
    assert [(f.pii_type, f.text) for f in found] == [
        ("EMAIL", "jane.doe@example.com"),
        ("EMP_ID", "EMP-40123"),
    ]
    assert all(f.detector == "rule" for f in found)


def test_fixture_resolves_the_achebe_cluster_across_files():
    blocks, rules = load_mock_p3()
    persons = [f for f in rules if f.pii_type == "PERSON"]
    evidence_findings = [f for f in rules if f.pii_type in ("EMAIL", "EMP_ID")]

    result = resolve_identities(persons, evidence_findings, blocks)

    by_name = {ident["canonical_name"]: ident for ident in result.identities}
    achebe = next(i for i in result.identities if "Achebe" in i["canonical_name"])
    assert len(achebe["mentions"]) == 3  # body, table row, slide
    assert "EMP_ID:EMP-40123" in achebe["linked_evidence"]
    assert "Dr. Priya Raman" in by_name
    assert result.conflicts == []
