"""End-to-end P1 -> (P2 skipped) -> P4 tests on a synthetic case document.

The NER-model test is skipped unless Presidio and the spaCy model are installed.
Everything else runs without optional dependencies.
"""

import json
import re

import docx
import pytest

from src.models.text_block import ExtractionResult
from src.pii import registry
from src.pii.contracts import Finding, validate_finding_dict
from src.pii.p4 import run_p4_report
from src.pipeline import extract_document

# No NER models and no P3, so the run is truly standalone.
NO_NER = {"enable_spacy": False, "enable_gliner": False, "use_p3": False}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
EMP_RE = re.compile(r"\bEMP-\d{4,}\b")


@pytest.fixture
def case_docx(tmp_path):
    """A DOCX with a 16.5 prose section and a roster table."""
    path = tmp_path / "case_file.docx"
    document = docx.Document()
    document.add_heading("16.5 Insider Activity", level=1)
    document.add_paragraph(
        "Michael T. Achebe, Senior Analyst, raised the alert. Reach him at "
        "michael.achebe@acme-corp.com or EMP-40123. Ticket RSK-2024-0031 covers the loss, "
        "estimated at $12,500."
    )
    table = document.add_table(rows=2, cols=3)
    table.rows[0].cells[0].text = "Name"
    table.rows[0].cells[1].text = "Employee"
    table.rows[0].cells[2].text = "Email"
    table.rows[1].cells[0].text = "M. T. Achebe"
    table.rows[1].cells[1].text = "EMP-40123"
    table.rows[1].cells[2].text = "m.achebe@acme-corp.com"
    document.add_heading("16.8 Third-Party Exposure", level=1)
    document.add_paragraph("The vendor Globex Ltd shared logs with Dr. Priya Raman.")
    document.save(str(path))
    return path


class RegexP3:
    """Stands in for the P3 detector: emits EMAIL and EMP_ID with detector='rule'."""

    def detect(self, blocks):
        findings = []
        for block in blocks:
            for pattern, pii_type in ((EMAIL_RE, "EMAIL"), (EMP_RE, "EMP_ID")):
                for match in pattern.finditer(block.text or ""):
                    findings.append(
                        Finding.from_block(
                            block, match.start(), match.end(), pii_type,
                            "rule", 0.99, ["rule:p3"],
                        )
                    )
        return findings


KNOWN_PEOPLE = ["Michael T. Achebe", "M. T. Achebe", "Michael Achebe", "Dr. Priya Raman"]


class FakeNER:
    """Deterministic stand-in for a NER model: tags known person names as PERSON."""

    name = "fake"

    def predict(self, text):
        from src.pii.backends import RawEntity

        out = []
        for person in KNOWN_PEOPLE:
            start = text.find(person)
            while start != -1:
                out.append(RawEntity(start, start + len(person), person, "PERSON", 0.9, self.name))
                start = text.find(person, start + 1)
        return out


@pytest.fixture
def mock_p3_registered():
    registry.clear_registered_detectors()
    registry.register_rule_detector(RegexP3())
    yield
    registry.clear_registered_detectors()


def test_default_pipeline_is_unchanged_without_enable_ner(case_docx):
    result = extract_document(case_docx)

    assert "p4" not in result.metadata
    assert not any("P4" in e for e in result.errors)
    assert result.total_blocks > 0


def test_enable_ner_without_models_degrades_and_warns(case_docx):
    registry.clear_registered_detectors()
    result = extract_document(case_docx, enable_ner=True, ner_config=NO_NER)

    p4 = result.metadata["p4"]
    assert p4["findings"] == []  # standalone + defer: nothing structured emitted
    assert p4["backends"] == []
    # Backends were disabled on purpose, so no "missing model" warning is expected.
    assert not any("NER backend" in e for e in result.errors)
    assert p4["counts"]["kept"] == 0


def test_missing_packages_warn_and_fall_back_without_crashing(case_docx, monkeypatch):
    from src.pii import backends

    backends.clear_model_cache()  # a cached model would hide the blocked import
    monkeypatch.setitem(__import__("sys").modules, "presidio_analyzer", None)
    monkeypatch.setitem(__import__("sys").modules, "gliner", None)
    registry.clear_registered_detectors()

    result = extract_document(case_docx, enable_ner=True, ner_config={"enable_spacy": True, "enable_gliner": True})

    p4 = result.metadata["p4"]
    assert p4["backends"] == []
    assert any("NER backend 'spacy' skipped" in e for e in result.errors)
    assert any("NER backend 'gliner' skipped" in e for e in result.errors)
    assert any("No NER backend" in e for e in result.errors)


def test_standalone_demo_emits_structured_pii_when_not_deferred(case_docx):
    registry.clear_registered_detectors()
    result = extract_document(
        case_docx,
        enable_ner=True,
        ner_config={**NO_NER, "defer_structured_to_rules": False},
    )

    types = {f["pii_type"] for f in result.metadata["p4"]["findings"]}
    assert {"EMAIL", "EMP_ID"} <= types
    for finding in result.metadata["p4"]["findings"]:
        assert validate_finding_dict(finding) == [], finding


def test_mock_p3_findings_are_used_and_internal_extractor_is_skipped(case_docx):
    base = extract_document(case_docx)
    rules = RegexP3().detect(base.blocks)

    report = run_p4_report(base.blocks, rules, {"defer_structured_to_rules": True}, backends=[FakeNER()])

    assert report.counts["rule_input"] == len(rules)
    sources = {s for f in report.findings for s in f.sources}
    assert "p4:linking" not in sources
    assert "rule:p3" in sources
    row_identity = [
        i for i in report.identities if any(m["text"] == "M. T. Achebe" for m in i["mentions"])
    ]
    assert row_identity and "EMAIL:m.achebe@acme-corp.com" in row_identity[0]["linked_evidence"]


def test_p4_output_is_json_serialisable_and_schema_valid(case_docx, mock_p3_registered):
    result = extract_document(case_docx, enable_ner=True, ner_config=NO_NER)

    payload = json.loads(result.to_json())
    findings = payload["metadata"]["p4"]["findings"]
    assert findings
    for finding in findings:
        assert validate_finding_dict(finding) == [], finding


def test_repeated_runs_give_identical_findings_apart_from_uuid_block_ids(case_docx, mock_p3_registered):
    def normalised(result):
        p4 = result.metadata["p4"]
        findings = [{k: v for k, v in f.items() if k != "block_id"} for f in p4["findings"]]
        return findings, p4["identities"]

    first = extract_document(case_docx, enable_ner=True, ner_config=NO_NER)
    second = extract_document(case_docx, enable_ner=True, ner_config=NO_NER)

    assert normalised(first) == normalised(second)


def test_rule_detector_failure_does_not_stop_p4(case_docx):
    class Broken:
        def detect(self, blocks):
            raise RuntimeError("P3 exploded")

    registry.clear_registered_detectors()
    registry.register_rule_detector(Broken())
    try:
        result = extract_document(case_docx, enable_ner=True, ner_config=NO_NER)
    finally:
        registry.clear_registered_detectors()

    assert "p4" in result.metadata
    assert any("P3 exploded" in e for e in result.errors)


def test_run_p4_accepts_blocks_from_several_documents_for_cross_file_identity(case_docx):
    base = extract_document(case_docx)
    blocks = list(base.blocks)
    # Second "document": same person, different file, initials-free name.
    second = ExtractionResult(source_file="briefing.pptx", source_type="PPTX")
    from src.models.text_block import TextBlock

    extra = TextBlock(
        block_id="slide-1",
        source_file="briefing.pptx",
        source_type="PPTX",
        block_type="slide",
        text="Michael Achebe escalated the case on the board.",
        slide_number=1,
        reading_order=0,
    )
    second.blocks = [extra]
    all_blocks = blocks + second.blocks

    report = run_p4_report(all_blocks, None, None, backends=[FakeNER()])

    achebe = [i for i in report.identities if "Achebe" in i["canonical_name"]]
    assert len(achebe) == 1
    files = {m["source_file"] for m in achebe[0]["mentions"]}
    assert files == {"case_file.docx", "briefing.pptx"}


def test_real_spacy_presidio_backend_when_installed(case_docx):
    pytest.importorskip("presidio_analyzer")
    spacy = pytest.importorskip("spacy")
    try:
        spacy.load("en_core_web_lg")
    except OSError:
        pytest.skip("en_core_web_lg not installed")

    registry.clear_registered_detectors()
    result = extract_document(
        case_docx,
        enable_ner=True,
        ner_config={"enable_gliner": False, "enable_spacy": True},
    )

    p4 = result.metadata["p4"]
    assert p4["backends"] == ["spacy"]
    persons = {f["text"] for f in p4["findings"] if f["pii_type"] == "PERSON"}
    assert any("Achebe" in t for t in persons)
    # IGNORE_PATTERNS: the RSK reference and the USD amount must never surface.
    assert not any("RSK-" in f["text"] or "$" in f["text"] for f in p4["findings"])
