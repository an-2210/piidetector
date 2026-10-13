"""Unit and integration test suite for P3 Rule-Based Detectors.

Covers all 15 required verification scenarios:
1. Valid email detection (trailing punctuation trimmed)
2. International phone-number detection and validation
3. Supported institutional identifiers (EMP, DIR, MER-IN, MER-PH, dictionary word exclusion)
4. Sensitive identifiers (SSN SSA rules, PAN, Passport, PSEF, TIN)
5. Card-number detection and Luhn algorithm validation
6. Context-aware DOB detection vs non-DOB dates
7. Address detection
8. False-positive suppression: RSK-, ISS-, INC-, GRP-POL-
9. False-positive suppression: Ordinary policy dates
10. False-positive suppression: USD amounts and financial ratios
11. Overlapping span de-conflicting and deduplication
12. TextBlock provenance and slice offset accuracy
13. Empty input, whitespace, and malformed TextBlocks
14. Unicode text and punctuation handling
15. End-to-end pipeline integration (P1 native + P2 OCR + P3 rule detection -> P4 schema)
"""

from pathlib import Path
import pytest

from src.detectors.filter import FalsePositiveFilter
from src.detectors.pipeline import RuleBasedDetector, run_detectors_pipeline
from src.detectors.validators import (
    luhn_checksum,
    validate_pan,
    validate_phone,
    validate_ssn,
    validate_tin,
)
from src.models.finding import Finding, FindingCategory, FindingsResult
from src.models.text_block import BlockType, SourceType, TextBlock
from src.pipeline import extract_and_detect, extract_document


def create_block(text: str, block_id: str = "blk-001", page: int = 1) -> TextBlock:
    """Helper fixture creating a synthetic TextBlock."""
    return TextBlock(
        block_id=block_id,
        source_file="synthetic_test_doc.pdf",
        source_type=SourceType.PDF.value,
        block_type=BlockType.BODY.value,
        text=text,
        page_number=page,
        reading_order=0,
        metadata={"source": "test_fixture"},
    )


# ==============================================================================
# 1. Email Address Detection
# ==============================================================================
def test_p3_detects_valid_email_and_trims_boundary_punctuation():
    detector = RuleBasedDetector()
    sample = "Please send records to security.lead@optiv-cadence.com. Additional info at support@cadence.org!"
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    emails = [f for f in findings if f.category == FindingCategory.EMAIL.value]

    assert len(emails) == 2
    assert emails[0].value == "security.lead@optiv-cadence.com"
    assert emails[1].value == "support@cadence.org"

    # Verify offset integrity: slicing block.text with offsets must match value exactly
    for f in emails:
        assert sample[f.start_offset:f.end_offset] == f.value
        assert not f.value.endswith(".")
        assert not f.value.endswith("!")


# ==============================================================================
# 2. International Phone Number Detection
# ==============================================================================
def test_p3_detects_international_phone_and_rejects_arbitrary_digits():
    detector = RuleBasedDetector()
    sample = (
        "Call us at +1-800-555-0199 or UK desk +44 20 7946 0919. "
        "India hotline is +91 98765 43210. Ignore ticket 123456 and dummy 000-000-0000."
    )
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    phones = [f for f in findings if f.category == FindingCategory.PHONE.value]

    phone_values = {f.value for f in phones}
    assert any("+1-800-555-0199" in p for p in phone_values)
    assert any("+44 20 7946 0919" in p for p in phone_values)
    assert any("+91 98765 43210" in p for p in phone_values)

    # Must reject dummy repeated digits and small arbitrary numbers
    assert "123456" not in phone_values
    assert "000-000-0000" not in phone_values

    for f in phones:
        assert sample[f.start_offset:f.end_offset] == f.value


# ==============================================================================
# 3. Institutional Identifiers (EMP, DIR, MER-IN, MER-PH)
# ==============================================================================
def test_p3_detects_institutional_identifiers_and_ignores_dictionary_words():
    detector = RuleBasedDetector()
    sample = (
        "Staff EMP-40123 reporting to DIR-9182. Vendor MER-IN-1049 and MER-PH-2051. "
        "Do NOT match DIRECTION or the board DIRECTOR."
    )
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    inst = [f for f in findings if f.category == FindingCategory.INSTITUTIONAL.value]
    inst_types = {f.identifier_type: f.value for f in inst}

    assert inst_types.get("EMP") == "EMP-40123"
    assert inst_types.get("DIR") == "DIR-9182"
    assert inst_types.get("MER-IN") == "MER-IN-1049"
    assert inst_types.get("MER-PH") == "MER-PH-2051"

    # Ensure DIRECTION and DIRECTOR were not captured
    all_values = [f.value for f in findings]
    assert "DIRECTION" not in all_values
    assert "DIRECTOR" not in all_values

    for f in inst:
        assert sample[f.start_offset:f.end_offset] == f.value


# ==============================================================================
# 4. Sensitive Identifiers (SSN, PAN, Passport, PSEF, TIN)
# ==============================================================================
def test_p3_detects_sensitive_identifiers_with_jurisdiction_rules():
    detector = RuleBasedDetector()
    sample = (
        "US Employee SSN: 219-45-7890. Indian PAN: ABCPE1234F. "
        "Tax TIN: 12-3456789. Filing code PSEF-9901-X. Passport Number: P98765432. "
        "Invalid SSNs to reject: 000-45-6789, 666-12-3456, 950-11-2233, 123-00-4567."
    )
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    sens = [f for f in findings if f.category == FindingCategory.SENSITIVE.value]
    by_type = {f.identifier_type: f.value for f in sens}

    assert by_type.get("SSN") == "219-45-7890"
    assert by_type.get("PAN") == "ABCPE1234F"
    assert by_type.get("TIN") == "12-3456789"
    assert by_type.get("PSEF") == "PSEF-9901-X"
    assert by_type.get("PASSPORT") == "P98765432"

    # SSA rule check: invalid areas/groups must not be captured as SSN
    ssn_findings = [f.value for f in sens if f.identifier_type == "SSN"]
    assert "000-45-6789" not in ssn_findings
    assert "666-12-3456" not in ssn_findings
    assert "950-11-2233" not in ssn_findings
    assert "123-00-4567" not in ssn_findings

    for f in sens:
        assert sample[f.start_offset:f.end_offset] == f.value


# ==============================================================================
# 5. Financial Identifiers & Luhn Check
# ==============================================================================
def test_p3_detects_valid_card_numbers_and_rejects_invalid_luhn():
    detector = RuleBasedDetector()
    # 4532-0150-1234-5671 is a valid Luhn test number
    valid_card = "4532-0150-1234-5671"
    # Tamper last digit -> 4532-0150-1234-5679 (fails Luhn)
    invalid_card = "4532-0150-1234-5679"

    sample = f"Payment card: {valid_card}. Corrupted card number: {invalid_card}."
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    cards = [f for f in findings if f.identifier_type == "CARD_NUMBER"]

    assert len(cards) == 1
    assert cards[0].value == valid_card
    assert sample[cards[0].start_offset:cards[0].end_offset] == valid_card


# ==============================================================================
# 6. Context-Aware DOB Detection
# ==============================================================================
def test_p3_detects_dob_with_context_and_ignores_standalone_dates():
    detector = RuleBasedDetector()
    sample = (
        "Client details: Date of Birth: 1985-04-12, place of birth Dallas. "
        "Document was created on September 16, 2026. Next review on 2027-01-01."
    )
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    dobs = [f for f in findings if f.identifier_type == "DOB"]

    assert len(dobs) == 1
    assert dobs[0].value == "1985-04-12"
    assert sample[dobs[0].start_offset:dobs[0].end_offset] == "1985-04-12"

    # Standalone dates without DOB context must NOT be captured as DOB
    all_dob_vals = [f.value for f in dobs]
    assert "September 16, 2026" not in all_dob_vals
    assert "2027-01-01" not in all_dob_vals


# ==============================================================================
# 7. Physical Address Detection
# ==============================================================================
def test_p3_detects_physical_addresses():
    detector = RuleBasedDetector()
    sample = "Headquarters located at 100 North Riverside Plaza, Suite 800, Chicago, IL 60606."
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    addrs = [f for f in findings if f.identifier_type == "ADDRESS"]

    assert len(addrs) >= 1
    assert "North Riverside Plaza" in addrs[0].value
    assert sample[addrs[0].start_offset:addrs[0].end_offset] == addrs[0].value


# ==============================================================================
# 8. False-Positive Control: Internal References (RSK-, ISS-, INC-, GRP-POL-)
# ==============================================================================
def test_p3_suppresses_internal_tracking_references():
    detector = RuleBasedDetector()
    sample = (
        "Reference tracker: RSK-1029, issue ticket ISS-404, incident INC-8821, "
        "and policy standard GRP-POL-6.0. Valid employee EMP-55123."
    )
    block = create_block(sample)

    findings, suppressed = detector.detect_block(block)
    values = [f.value for f in findings]

    assert "RSK-1029" not in values
    assert "ISS-404" not in values
    assert "INC-8821" not in values
    assert "GRP-POL-6.0" not in values

    # Valid employee MUST remain detected
    assert "EMP-55123" in values
    assert suppressed >= 4


# ==============================================================================
# 9. False-Positive Control: Policy Dates
# ==============================================================================
def test_p3_suppresses_policy_and_governance_dates():
    detector = RuleBasedDetector()
    sample = (
        "Effective Date: 2024-01-15. Policy Review Date: 2025-06-30. "
        "Approved on 2023-11-20. Client DOB: 1992-08-25."
    )
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    dob_values = [f.value for f in findings if f.identifier_type == "DOB"]

    assert "1992-08-25" in dob_values
    assert "2024-01-15" not in dob_values
    assert "2025-06-30" not in dob_values
    assert "2023-11-20" not in dob_values


# ==============================================================================
# 10. False-Positive Control: USD Amounts and Financial Ratios
# ==============================================================================
def test_p3_suppresses_amounts_and_financial_ratios():
    detector = RuleBasedDetector()
    sample = (
        "Total portfolio allocation $150,000 and budget 2,500,000 USD. "
        "Leverage ratio is 2.4x and debt-to-equity is 3:1 with 75% margin. "
        "Customer account ending in 4102."
    )
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    card_and_account = [f for f in findings if f.category == FindingCategory.FINANCIAL.value]

    values = [f.value for f in card_and_account]
    assert "$150,000" not in values
    assert "2,500,000 USD" not in values
    assert "2.4x" not in values
    assert "3:1" not in values
    assert "75%" not in values

    # Account last 4 is legitimate
    assert any(f.identifier_type == "ACCOUNT_LAST4" and f.value == "4102" for f in card_and_account)


# ==============================================================================
# 11. Overlapping Spans De-conflicting & Deduplication
# ==============================================================================
def test_p3_resolves_overlapping_spans_and_deduplicates():
    detector = RuleBasedDetector()
    # A 16-digit card number should not also trigger a conflicting last-4 or partial number
    valid_card = "4532-0150-1234-5671"
    sample = f"Card details: {valid_card} and again {valid_card}."
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    card_findings = [f for f in findings if f.identifier_type == "CARD_NUMBER"]

    # Deduplicated by start_offset: 2 distinct occurrences in string
    assert len(card_findings) == 2
    assert card_findings[0].value == valid_card
    assert card_findings[1].value == valid_card

    # No overlapping ACCOUNT_LAST4 should collide with the card span
    acc_last4 = [
        f for f in findings
        if f.identifier_type == "ACCOUNT_LAST4"
        and (f.start_offset >= card_findings[0].start_offset and f.end_offset <= card_findings[0].end_offset)
    ]
    assert len(acc_last4) == 0


# ==============================================================================
# 12. TextBlock Provenance and Offset Integrity
# ==============================================================================
def test_p3_verifies_block_provenance_and_offsets():
    detector = RuleBasedDetector()
    sample = "User EMP-12345 registered email user.one@cadence.com on system."
    block = create_block(sample, block_id="custom-uuid-42", page=3)

    findings, _ = detector.detect_block(block)
    assert len(findings) == 2

    for f in findings:
        assert f.text_block_id == "custom-uuid-42"
        assert f.detector == "rule"
        assert f.confidence == 1.0
        # Character offsets must slice the exact value
        assert sample[f.start_offset:f.end_offset] == f.value
        assert len(f.context) > 0


# ==============================================================================
# 13. Empty and Malformed TextBlock Handling
# ==============================================================================
def test_p3_handles_empty_whitespace_and_malformed_blocks():
    detector = RuleBasedDetector()

    empty_block = create_block("")
    f1, s1 = detector.detect_block(empty_block)
    assert f1 == []
    assert s1 == 0

    ws_block = create_block("   \n\t   ")
    f2, s2 = detector.detect_block(ws_block)
    assert f2 == []
    assert s2 == 0

    none_block = TextBlock(block_id="b-none", text=None)
    f3, s3 = detector.detect_block(none_block)
    assert f3 == []
    assert s3 == 0

    res = detector.detect_blocks([empty_block, ws_block, none_block])
    assert res.total_findings == 0
    assert res.findings == []


# ==============================================================================
# 14. Unicode Text and Punctuation Handling
# ==============================================================================
def test_p3_handles_unicode_characters_and_preserves_exact_offsets():
    detector = RuleBasedDetector()
    # Text contains Unicode characters (é, ü, em-dash —, curly quotes)
    sample = "Directeur Général Hélène René: EMP-99812 — Courriel: helene.rene@societe.fr."
    block = create_block(sample)

    findings, _ = detector.detect_block(block)
    assert len(findings) == 2

    by_type = {f.identifier_type: f for f in findings}
    emp_f = by_type["EMP"]
    email_f = by_type["EMAIL"]

    assert emp_f.value == "EMP-99812"
    assert email_f.value == "helene.rene@societe.fr"

    # Strict Unicode character offset slicing verification
    assert sample[emp_f.start_offset:emp_f.end_offset] == "EMP-99812"
    assert sample[email_f.start_offset:email_f.end_offset] == "helene.rene@societe.fr"


# ==============================================================================
# 15. End-to-End Pipeline Integration (P1 + P2 + P3 -> P4 Contract)
# ==============================================================================
def test_p3_end_to_end_pipeline_integration(tmp_path: Path):
    """Test full document flow: extract_and_detect() produces valid P4 findings."""
    import docx

    doc_path = tmp_path / "cadence_audit_record.docx"
    doc = docx.Document()
    doc.add_heading("Employee Compliance Record", level=1)
    doc.add_paragraph("Employee ID: EMP-40123")
    doc.add_paragraph("Official email: compliance.officer@cadence.com")
    doc.add_paragraph("Personal SSN: 219-45-7890")
    doc.add_paragraph("Internal Audit Reference: RSK-9002 (do not redact)")
    doc.save(str(doc_path))

    # Run unified extract_and_detect
    extraction_result, findings_result = extract_and_detect(doc_path)

    # 1. P1 Extraction assertions
    assert len(extraction_result.blocks) >= 4
    assert extraction_result.source_type == "DOCX"

    # 2. P3 Findings assertions
    assert findings_result.total_findings >= 3
    found_types = {f.identifier_type for f in findings_result.findings}
    assert "EMP" in found_types
    assert "EMAIL" in found_types
    assert "SSN" in found_types

    # 3. P4 Contract schema verification
    for finding in findings_result.findings:
        d = finding.to_dict()
        assert "finding_id" in d and len(d["finding_id"]) > 0
        assert d["detector"] == "rule"
        assert d["category"] in [c.value for c in FindingCategory]
        assert "value" in d and len(d["value"]) > 0
        assert isinstance(d["start_offset"], int)
        assert isinstance(d["end_offset"], int)
        assert d["end_offset"] > d["start_offset"]
        assert d["text_block_id"] is not None
        assert 0.0 <= d["confidence"] <= 1.0
        assert isinstance(d["context"], str)
        assert isinstance(d["metadata"], dict)

    # Verify suppressed count contains RSK-9002
    assert findings_result.suppressed_count >= 1
    values = [f.value for f in findings_result.findings]
    assert "RSK-9002" not in values
