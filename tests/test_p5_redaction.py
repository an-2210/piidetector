from src.models.text_block import TextBlock
from src.p5 import build_exposure_report, check_llm_safety, redact_blocks


def block(text="Contact Rahul Sharma at rahul@example.com; employee ID EMP-1024."):
    return TextBlock(
        block_id="b1", source_file="sample.docx", source_type="DOCX",
        block_type="body", text=text,
    )


def test_redacts_offsets_and_reuses_stable_tokens():
    b = block()
    findings = [
        {"block_id": "b1", "start": 8, "end": 20, "text": "Rahul Sharma", "pii_type": "PERSON", "identity_id": "person-1"},
        {"block_id": "b1", "start": 24, "end": 41, "text": "rahul@example.com", "pii_type": "EMAIL"},
        {"block_id": "b1", "start": 55, "end": 63, "text": "EMP-1024", "pii_type": "EMP_ID"},
    ]
    result = redact_blocks([b], findings)
    assert "[PERSON_1]" in result.redacted_text
    assert "[EMAIL_1]" in result.redacted_text
    assert "[EMPLOYEE_ID_1]" in result.redacted_text
    assert "Rahul Sharma" not in result.redacted_text
    assert check_llm_safety(result)["safe"] is True
    assert build_exposure_report(result)["summary"]["redacted_findings"] == 3


def test_invalid_span_fails_closed():
    b = block("SSN: 123-45-6789")
    result = redact_blocks([b], [{"block_id": "b1", "start": 5, "end": 16, "text": "not-the-value", "pii_type": "SSN"}])
    assert result.unresolved_findings
    assert check_llm_safety(result)["safe"] is False
    assert check_llm_safety(result)["status"] == "BLOCKED"


def test_token_registry_reuses_same_value_across_blocks():
    registry = {}
    b1 = TextBlock(block_id="a", source_file="one.docx", text="x@example.com")
    b2 = TextBlock(block_id="b", source_file="two.docx", text="x@example.com")
    r1 = redact_blocks([b1], [{"block_id": "a", "start": 0, "end": 13, "text": "x@example.com", "pii_type": "EMAIL"}], registry)
    r2 = redact_blocks([b2], [{"block_id": "b", "start": 0, "end": 13, "text": "x@example.com", "pii_type": "EMAIL"}], registry)
    assert r1.redacted_text == r2.redacted_text == "[EMAIL_1]"
