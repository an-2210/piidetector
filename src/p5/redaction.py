"""P5 redaction utilities compatible with the repository's P4 finding contract.

Findings use character offsets into TextBlock.text and labels from src.pii.contracts.
Reports deliberately omit original PII values.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from src.models.text_block import TextBlock

HIGH_RISK_TYPES = {
    "SSN", "PAN", "PASSPORT", "PESEL", "TIN", "CARD_NUMBER",
    "CARD_LAST4", "ACCOUNT_LAST4", "EMP_ID", "DIR_ID", "MER_IN_ID", "MER_PH_ID",
}
TOKEN_LABELS = {
    "PERSON": "PERSON", "ORG": "ORG", "ADDRESS": "ADDRESS", "EMAIL": "EMAIL",
    "PHONE": "PHONE", "EMP_ID": "EMPLOYEE_ID", "DIR_ID": "DIR_ID",
    "MER_IN_ID": "MER_IN_ID", "MER_PH_ID": "MER_PH_ID", "SSN": "SSN",
    "PAN": "PAN", "PASSPORT": "PASSPORT", "PESEL": "PESEL", "TIN": "TIN",
    "CARD_LAST4": "CARD_LAST4", "ACCOUNT_LAST4": "ACCOUNT_LAST4", "DOB": "DOB",
    "CARD_NUMBER": "CARD_NUMBER", "PSEF": "PSEF",
}

@dataclass
class RedactionResult:
    source_file: str
    redacted_blocks: List[Dict[str, Any]]
    findings: List[Dict[str, Any]]
    unresolved_findings: List[Dict[str, Any]]
    token_map: Dict[str, str] = field(default_factory=dict, repr=False)
    # (original value, token) pairs, kept in memory only for native-format export. Never serialized.
    replacements: List[Tuple[str, str]] = field(default_factory=list, repr=False)

    @property
    def redacted_text(self) -> str:
        return "\n\n".join(block["redacted_text"] for block in self.redacted_blocks)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "total_findings": len(self.findings) + len(self.unresolved_findings),
            "redacted_findings": len(self.findings),
            "unresolved_findings": len(self.unresolved_findings),
            "findings": self.findings,
            "unresolved": self.unresolved_findings,
        }


def _get(finding: Any, key: str, default: Any = None) -> Any:
    if isinstance(finding, Mapping):
        return finding.get(key, default)
    return getattr(finding, key, default)


def _normalize_type(finding: Any) -> str:
    return str(_get(finding, "pii_type", _get(finding, "identifier_type", "PII"))).upper()


def _span(finding: Any) -> Tuple[int, int]:
    start = _get(finding, "start", _get(finding, "start_offset", None))
    end = _get(finding, "end", _get(finding, "end_offset", None))
    if start is None or end is None:
        raise ValueError("Finding is missing start/end offsets")
    return int(start), int(end)


def _block_id(finding: Any) -> str:
    return str(_get(finding, "block_id", _get(finding, "text_block_id", "")))


def _stable_key(finding: Any, pii_type: str, value: str) -> str:
    identity = _get(finding, "identity_id", None)
    if identity:
        return f"identity:{identity}"
    # Repeated identical values of a given PII type receive the same token across files.
    clean_val = re.sub(r"\s+", " ", value).strip().casefold()
    return f"value:{pii_type}:{clean_val}"


def redact_blocks(
    blocks: Sequence[TextBlock],
    findings: Sequence[Any],
    token_registry: Dict[str, str] | None = None,
) -> RedactionResult:
    """Redact P4/P3 findings in TextBlocks using stable, type-specific tokens.

    A caller can pass the same token_registry across documents to maintain token
    consistency across a batch. Findings must provide block ID and character offsets.
    """
    registry = token_registry if token_registry is not None else {}
    by_block = {b.block_id: b for b in blocks}
    grouped: Dict[str, List[Any]] = {}
    unresolved: List[Dict[str, Any]] = []
    for finding in findings:
        bid = _block_id(finding)
        block = by_block.get(bid)
        pii_type = _normalize_type(finding)
        try:
            start, end = _span(finding)
        except (ValueError, TypeError):
            unresolved.append({"type": pii_type, "reason": "missing_or_invalid_offsets", "block_id": bid})
            continue
        value = str(_get(finding, "text", _get(finding, "value", "")))
        if block is None:
            unresolved.append({"type": pii_type, "reason": "unknown_block", "block_id": bid})
            continue
        if start < 0 or end <= start or end > len(block.text):
            unresolved.append({"type": pii_type, "reason": "out_of_range_offsets", "block_id": bid})
            continue
        actual = block.text[start:end]
        if value and actual != value:
            unresolved.append({"type": pii_type, "reason": "span_value_mismatch", "block_id": bid})
            continue
        finding_data = {
            "block_id": bid, "start": start, "end": end, "type": pii_type,
            "value": actual, "identity_id": _get(finding, "identity_id", None),
            "confidence": _get(finding, "confidence", None),
            "source_file": block.source_file,
        }
        grouped.setdefault(bid, []).append(finding_data)

    safe_findings: List[Dict[str, Any]] = []
    redacted_blocks: List[Dict[str, Any]] = []
    pair_list: List[Tuple[str, str]] = []
    for block in blocks:
        spans = sorted(grouped.get(block.block_id, []), key=lambda f: (f["start"], f["end"]))
        # Overlapping spans are ambiguous; fail closed rather than partially redact.
        selected: List[Dict[str, Any]] = []
        for item in spans:
            if selected and item["start"] < selected[-1]["end"]:
                unresolved.append({"type": item["type"], "reason": "overlapping_findings", "block_id": block.block_id})
                continue
            selected.append(item)
        redacted = block.text
        replacements = []
        for item in selected:
            label = TOKEN_LABELS.get(item["type"], re.sub(r"[^A-Z0-9_]+", "_", item["type"]))
            key = _stable_key({"identity_id": item["identity_id"]}, item["type"], item["value"])
            if key not in registry:
                prefix = f"[{label}_"
                used = {v for v in registry.values() if v.startswith(prefix)}
                n = 1
                while f"{prefix}{n}]" in used:
                    n += 1
                registry[key] = f"{prefix}{n}]"
            token = registry[key]
            replacements.append((item["start"], item["end"], token, item))
            pair_list.append((item["value"], token))
        for start, end, token, item in reversed(replacements):
            redacted = redacted[:start] + token + redacted[end:]
        for _, _, token, item in replacements:
            safe_findings.append({
                "source_file": item["source_file"], "block_id": item["block_id"],
                "type": item["type"], "token": token, "redacted": True,
                "confidence": item["confidence"],
                "location": {"page": block.page_number, "slide": block.slide_number,
                             "block_type": block.block_type},
            })
        redacted_blocks.append({
            "block_id": block.block_id, "source_file": block.source_file,
            "source_type": block.source_type, "block_type": block.block_type,
            "page_number": block.page_number, "slide_number": block.slide_number,
            "redacted_text": redacted,
        })

    return RedactionResult(
        source_file=blocks[0].source_file if blocks else "unknown",
        redacted_blocks=redacted_blocks,
        findings=safe_findings,
        unresolved_findings=unresolved,
        token_map=registry,
        replacements=list(dict.fromkeys(pair_list)),
    )


def check_llm_safety(result: RedactionResult) -> Dict[str, Any]:
    """Fail closed when a high-risk finding could not be safely redacted."""
    high_risk_unresolved = [
        f for f in result.unresolved_findings if str(f.get("type", "")).upper() in HIGH_RISK_TYPES
    ]
    safe = not result.unresolved_findings and not high_risk_unresolved
    return {
        "safe": safe,
        "status": "PASS" if safe else "BLOCKED",
        "message": "No known unresolved findings." if safe else "Unresolved findings remain; do not send this content to an LLM.",
        "unresolved_count": len(result.unresolved_findings),
        "high_risk_unresolved_count": len(high_risk_unresolved),
    }


def build_exposure_report(result: RedactionResult) -> Dict[str, Any]:
    counts = Counter(f["type"] for f in result.findings)
    unresolved_counts = Counter(f["type"] for f in result.unresolved_findings)
    safety = check_llm_safety(result)
    return {
        "source_file": result.source_file,
        "summary": {
            "total_findings": len(result.findings) + len(result.unresolved_findings),
            "redacted_findings": len(result.findings),
            "unresolved_findings": len(result.unresolved_findings),
            "by_type": dict(sorted(counts.items())),
            "unresolved_by_type": dict(sorted(unresolved_counts.items())),
        },
        "llm_safety_gate": safety,
        "findings": result.to_dict()["findings"],
        "unresolved": result.unresolved_findings,
    }


def write_json(data: Mapping[str, Any], path: str) -> None:
    """Write a JSON artifact using UTF-8 and stable indentation."""
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
