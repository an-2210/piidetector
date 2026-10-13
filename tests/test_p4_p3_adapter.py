"""The P3 adapter maps every identifier type P3 emits, and drops only non-PII markers."""

from src.models.finding import Finding as P3Finding, FindingsResult
from src.pii.p3_adapter import P3_NOT_PII, P3_TO_PII, P3RuleAdapter
from tests.p4_support import make_block


class StubP3:
    def __init__(self, findings):
        self.findings = findings

    def detect_blocks(self, blocks, source_file=""):
        return FindingsResult(findings=self.findings, total_findings=len(self.findings))


def test_new_p3_types_pesel_and_card_last4_are_mapped():
    block = make_block("PESEL: 80010112345. Card ending 4421.", block_id="b")
    text = block.text
    raw = [
        P3Finding(identifier_type="PESEL", value="80010112345", start_offset=text.index("8001"),
                  end_offset=text.index("8001") + 11, text_block_id="b", confidence=0.8),
        P3Finding(identifier_type="CARD_LAST4", value="4421", start_offset=text.index("4421"),
                  end_offset=text.index("4421") + 4, text_block_id="b"),
    ]
    adapter = P3RuleAdapter(detector=StubP3(raw))

    out = adapter.detect([block])

    assert [(f.pii_type, f.text, f.owner) for f in out] == [
        ("PESEL", "80010112345", "p3"),
        ("CARD_LAST4", "4421", "p3"),
    ]
    assert adapter.last_stats["p3_unknown_type"] == 0


def test_internal_ref_marker_is_dropped_not_mapped():
    assert "INTERNAL_REF" in P3_NOT_PII
    assert "INTERNAL_REF" not in P3_TO_PII
