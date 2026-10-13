"""ORG false-positive decoys, ORG-to-PERSON relabelling, and the emit_org flag."""

import pytest

from src.pii.backends import RawEntity
from src.pii.config import P4Config
from src.pii.disambiguate import org_false_positive_reason
from src.pii.p4 import run_p4_report
from tests.p4_support import make_block

CFG = P4Config()


class FakeNER:
    """Deterministic backend: tags each given string wherever it occurs in the text."""

    name = "fake"

    def __init__(self, tags):
        self.tags = tags  # {text: (label, score)}

    def predict(self, text):
        out = []
        for needle, (label, score) in self.tags.items():
            start = text.find(needle)
            while start != -1:
                out.append(RawEntity(start, start + len(needle), needle, label, score, self.name))
                start = text.find(needle, start + 1)
        return out


# --- 1. ORG false-positive decoys, one test per category -----------------------

@pytest.mark.parametrize("text", ["Audit", "Finance", "Legal", "Compliance", "HR", "Risk"])
def test_single_generic_word_is_not_an_org(text):
    assert org_false_positive_reason(text, CFG) == "generic_word"


@pytest.mark.parametrize("text", ["Head of Audit", "Director of Finance", "Chief Risk Officer"])
def test_role_phrase_is_not_an_org(text):
    assert org_false_positive_reason(text, CFG) == "role_phrase"


@pytest.mark.parametrize("text", ["the Risk Committee", "the Audit Board", "the Lagos Operations Team", "the Compliance Unit", "Lagos Operations Team"])
def test_governance_unit_phrase_is_not_an_org(text):
    assert org_false_positive_reason(text, CFG) == "unit_phrase"


@pytest.mark.parametrize("text", ["SSN", "Email", "Phone", "DOB", "TIN", "PESEL", "PAN"])
def test_pii_field_label_is_not_an_org(text):
    assert org_false_positive_reason(text, CFG) == "pii_field_label"


@pytest.mark.parametrize("text", ["Globex Ltd", "Acme Corp", "Northwind Logistics Ltd", "Achebe Holdings Ltd", "Admiralty Way"])
def test_real_organisations_and_suffixed_names_are_kept(text):
    assert org_false_positive_reason(text, CFG) is None


def test_filter_lists_are_config_driven():
    relaxed = P4Config(org_generic_words=(), org_filter_enabled=True)
    assert org_false_positive_reason("Audit", relaxed) is None


def test_filter_drops_candidates_in_the_pipeline_and_counts_them():
    block = make_block("Head of Audit checked the SSN and the Risk Committee.", block_id="b")
    backend = FakeNER({"Audit": ("ORG", 0.85), "SSN": ("ORG", 0.85), "the Risk Committee": ("ORG", 0.85)})

    report = run_p4_report([block], None, {"defer_structured_to_rules": True}, backends=[backend])

    assert [f.pii_type for f in report.findings if f.pii_type == "ORG"] == []
    assert report.counts["org_filtered"] == 3


def test_filter_can_be_switched_off():
    block = make_block("Head of Audit checked it.", block_id="b")
    backend = FakeNER({"Audit": ("ORG", 0.85)})

    report = run_p4_report([block], None, {"org_filter_enabled": False, "defer_structured_to_rules": True}, backends=[backend])

    assert [f.text for f in report.findings if f.pii_type == "ORG"] == ["Audit"]


# --- 2. Relabelling ORG to PERSON ---------------------------------------------

def _grace_table():
    content = [["Name", "Employee"], ["Grace Achebe", "EMP-40987"]]
    return make_block(
        "| Name | Employee |\n| --- | --- |\n| Grace Achebe | EMP-40987 |",
        block_id="t", block_type="table", content=content, reading_order=3,
    )


def test_table_header_forces_org_in_a_name_column_to_person_and_links_it():
    prose = make_block("Grace Achebe, Head of Audit, signed off.", block_id="p", reading_order=1)
    table = _grace_table()
    backend = FakeNER({"Grace Achebe": ("PERSON", 0.9)})
    # The table cell is tagged ORG by the model; the prose mention is PERSON.
    class Mixed:
        name = "fake"

        def predict(self, text):
            if text.startswith("| Name"):
                return [RawEntity(text.index("Grace Achebe"), text.index("Grace Achebe") + 12, "Grace Achebe", "ORG", 0.85, "fake")]
            return backend.predict(text)

    report = run_p4_report([prose, table], None, {"defer_structured_to_rules": True}, backends=[Mixed()])

    table_finding = next(f for f in report.findings if f.block_id == "t")
    prose_finding = next(f for f in report.findings if f.block_id == "p")
    assert table_finding.pii_type == "PERSON"
    assert "p4:table_header" in table_finding.sources
    assert table_finding.identity_id is not None
    assert table_finding.identity_id == prose_finding.identity_id


def test_org_with_legal_suffix_in_a_name_column_stays_org():
    table = make_block(
        "| Name | Employee |\n| --- | --- |\n| Achebe Holdings Ltd | EMP-1 |",
        block_id="t", block_type="table",
        content=[["Name", "Employee"], ["Achebe Holdings Ltd", "EMP-1"]], reading_order=0,
    )
    backend = FakeNER({"Achebe Holdings Ltd": ("ORG", 0.9)})

    report = run_p4_report([table], None, {"defer_structured_to_rules": True}, backends=[backend])

    assert [f.pii_type for f in report.findings] == ["ORG"]


def test_org_that_matches_a_resolved_person_is_relabelled_and_linked():
    people = make_block("Grace Achebe signed the review.", block_id="p1", reading_order=1)
    mention = make_block("The memo was sent by Grace Achebe to finance.", block_id="p2", reading_order=2)
    backend = FakeNER({"Grace Achebe": ("PERSON", 0.9)})

    class Second:
        name = "fake"

        def predict(self, text):
            if text.startswith("The memo"):
                return [RawEntity(text.index("Grace"), text.index("Grace") + 12, "Grace Achebe", "ORG", 0.85, "fake")]
            return backend.predict(text)

    report = run_p4_report([people, mention], None, {"defer_structured_to_rules": True}, backends=[Second()])

    relabelled = next(f for f in report.findings if f.block_id == "p2")
    assert relabelled.pii_type == "PERSON"
    assert "p4:identity_link" in relabelled.sources
    assert relabelled.identity_id == next(f for f in report.findings if f.block_id == "p1").identity_id


def test_org_with_legal_suffix_matching_a_person_surname_stays_org():
    people = make_block("Michael Achebe signed the review.", block_id="p1", reading_order=1)
    org = make_block("Achebe Holdings Ltd pays the fee.", block_id="p2", reading_order=2)
    backend = FakeNER({"Michael Achebe": ("PERSON", 0.9), "Achebe Holdings Ltd": ("ORG", 0.9)})

    report = run_p4_report([people, org], None, {"defer_structured_to_rules": True}, backends=[backend])

    assert next(f for f in report.findings if f.block_id == "p2").pii_type == "ORG"


def test_ambiguous_first_last_match_is_not_relabelled():
    # "Michael T. Achebe" and "Michael O. Achebe" are different people, and "Michael Achebe"
    # fits both. The ORG span must stay ORG rather than pick one.
    a = make_block("Michael T. Achebe reviewed it.", block_id="a", reading_order=1)
    b = make_block("Michael O. Achebe reviewed it.", block_id="b", reading_order=2)
    c = make_block("Michael Achebe was copied.", block_id="c", reading_order=3)

    class Tagged:
        name = "fake"

        def predict(self, text):
            if text.startswith("Michael Achebe was"):
                return [RawEntity(0, 14, "Michael Achebe", "ORG", 0.85, "fake")]
            if text.startswith("Michael T."):
                return [RawEntity(0, 16, "Michael T. Achebe", "PERSON", 0.9, "fake")]
            return [RawEntity(0, 16, "Michael O. Achebe", "PERSON", 0.9, "fake")]

    report = run_p4_report([a, b, c], None, {"defer_structured_to_rules": True}, backends=[Tagged()])

    assert next(f for f in report.findings if f.block_id == "c").pii_type == "ORG"
    assert len({f.identity_id for f in report.findings if f.pii_type == "PERSON"}) == 2


# --- 3. emit_org flag ----------------------------------------------------------

def test_emit_org_false_hides_org_but_keeps_relabelled_persons():
    prose = make_block("Grace Achebe reviewed it. Acme Corp sent the file.", block_id="p", reading_order=1)
    table = _grace_table()

    class Tagger:
        name = "fake"

        def predict(self, text):
            out = []
            if text.startswith("| Name"):
                out.append(RawEntity(text.index("Grace Achebe"), text.index("Grace Achebe") + 12, "Grace Achebe", "ORG", 0.85, "fake"))
            else:
                out.append(RawEntity(text.index("Grace Achebe"), text.index("Grace Achebe") + 12, "Grace Achebe", "PERSON", 0.9, "fake"))
                out.append(RawEntity(text.index("Acme Corp"), text.index("Acme Corp") + 9, "Acme Corp", "ORG", 0.9, "fake"))
            return out

    report = run_p4_report([prose, table], None, {"defer_structured_to_rules": True, "emit_org": False}, backends=[Tagger()])

    types = [(f.block_id, f.pii_type) for f in report.findings]
    assert ("t", "PERSON") in types  # relabelled before the ORG drop
    assert all(pii != "ORG" for _, pii in types)
    assert report.counts["org_suppressed"] == 1  # Acme Corp


@pytest.mark.parametrize("text", ["Finance and Legal", "Legal & Compliance", "HR or Audit", "Risk Committee"])
def test_conjunction_of_generic_words_is_not_an_org(text):
    assert org_false_positive_reason(text, CFG) == "generic_word"


def test_conjunction_with_a_real_name_is_kept():
    assert org_false_positive_reason("Finance and Globex", CFG) is None


def test_ner_address_without_structure_is_dropped_and_counted():
    block = make_block("The Lagos office handled the case.", block_id="b")
    backend = FakeNER({"Lagos office": ("ADDRESS", 0.9)})

    report = run_p4_report([block], None, {"defer_structured_to_rules": True}, backends=[backend])

    assert [f for f in report.findings if f.pii_type == "ADDRESS"] == []
    assert report.counts["address_unstructured"] == 1


def test_ner_address_with_a_house_number_is_kept():
    block = make_block("Sent to 22 Allen Avenue today.", block_id="b")
    backend = FakeNER({"22 Allen Avenue": ("ADDRESS", 0.9)})

    report = run_p4_report([block], None, {"defer_structured_to_rules": True}, backends=[backend])

    assert [f.text for f in report.findings if f.pii_type == "ADDRESS"] == ["22 Allen Avenue"]


def test_backend_disagreement_in_a_name_column_is_resolved_as_person():
    table = _grace_table()

    class Disagree:
        name = "fake"

        def predict(self, text):
            start = text.index("Grace Achebe")
            return [
                RawEntity(start, start + 12, "Grace Achebe", "ORG", 0.85, "spacy"),
                RawEntity(start, start + 12, "Grace Achebe", "PERSON", 0.93, "gliner"),
            ]

    report = run_p4_report([table], None, {"defer_structured_to_rules": True}, backends=[Disagree()])

    grace = [f for f in report.findings if f.text == "Grace Achebe"]
    assert [f.pii_type for f in grace] == ["PERSON"]
    assert grace[0].confidence >= 0.5


def test_equal_span_type_conflict_prefers_the_higher_score():
    from src.pii.contracts import Finding
    from src.pii.fusion import fuse

    block = make_block("Grace Achebe signed.", block_id="b")
    org = Finding.from_block(block, 0, 12, "ORG", "ner", 0.6, ["ner:spacy"])
    person = Finding.from_block(block, 0, 12, "PERSON", "ner", 0.9, ["ner:gliner"])

    assert [f.pii_type for f in fuse([], [org, person], CFG).kept] == ["PERSON"]
