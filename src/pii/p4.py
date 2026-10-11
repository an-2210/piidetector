"""P4 entry point: NER candidates, fusion and entity resolution.

`run_p4` is the public seam. Pass rule findings from P3 when they exist, or
None / [] for standalone mode. `run_p4_report` returns the same findings plus
warnings, identities, debug output and counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Union

from src.models.text_block import TextBlock
from src.pii.address import find_addresses
from src.pii.backends import NERBackend, load_backends
from src.pii.config import P4Config
from src.pii.contracts import DETECTORS, PII_TYPES, Finding, ignore_spans, overlaps_ignore
from src.pii.disambiguate import decide_label, org_false_positive_reason
from src.pii.fusion import fuse
from src.pii.linking import extract_evidence
from src.pii.prose import block_weight, in_priority_section, is_id_like
from src.pii.relabel import force_person_by_header, relabel_org_by_identity
from src.pii.resolve import resolve_identities

ConfigLike = Union[P4Config, Dict[str, Any], None]


@dataclass
class P4Report:
    """Full P4 output: findings plus everything needed to audit a run."""

    findings: List[Finding]
    identities: List[dict] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    backends: List[str] = field(default_factory=list)
    counts: Dict[str, int] = field(default_factory=dict)
    debug: List[Finding] = field(default_factory=list)
    debug_ignored: List[Finding] = field(default_factory=list)

    def to_dict(self, include_debug: bool = False) -> Dict[str, Any]:
        """JSON-serialisable view. Debug candidates are included only when requested."""
        data: Dict[str, Any] = {
            "findings": [f.to_dict() for f in self.findings],
            "identities": self.identities,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
            "backends": self.backends,
            "counts": self.counts,
        }
        if include_debug:
            data["debug"] = [f.to_dict() for f in self.debug]
            data["debug_ignored"] = [f.to_dict() for f in self.debug_ignored]
        return data


def _ner_candidates(
    blocks: Sequence[TextBlock],
    backends: Sequence[NERBackend],
    config: P4Config,
    warnings: List[str],
    ignored: List[Finding],
    stats: Dict[str, int],
) -> List[Finding]:
    """Turn raw backend spans into adjusted NER Findings, block by block."""
    candidates: List[Finding] = []
    for block in blocks:
        text = block.text or ""
        if not text.strip():
            continue

        raw = []
        for backend in backends:
            try:
                raw.extend(backend.predict(text))
            except Exception as exc:  # noqa: BLE001 - one backend failing must not stop the rest
                warnings.append(f"NER backend '{backend.name}' failed on block {block.block_id}: {exc}")
        # LOCATION is a place cue. It only extends address matches and is never a PII candidate.
        places = [(r.start, r.end) for r in raw if r.label == "LOCATION"]
        raw = [r for r in raw if r.label != "LOCATION"]

        spans_to_ignore = ignore_spans(text)
        weight = block_weight(block, config)
        priority = in_priority_section(block, config)

        # Deterministic address pattern. It runs even with no NER backend.
        for address in find_addresses(text, places, config):
            if overlaps_ignore(address.start, address.end, spans_to_ignore):
                continue
            confidence = address.confidence * weight + (config.priority_boost if priority else 0.0)
            candidates.append(
                Finding.from_block(
                    block,
                    address.start,
                    address.end,
                    "ADDRESS",
                    "ner",
                    round(min(1.0, confidence), 4),
                    ["p4:address_pattern"],
                    owner="p4",
                )
            )

        for entity in raw:
            if overlaps_ignore(entity.start, entity.end, spans_to_ignore):
                ignored.append(
                    Finding.from_block(
                        block, entity.start, entity.end, entity.label,
                        "ner", entity.score, [f"ner:{entity.backend}"],
                    )
                )
                continue

            overlapping = {
                other.label
                for other in raw
                if other.start < entity.end and entity.start < other.end
            }
            decision = decide_label(
                entity.text, entity.label, text, entity.start, entity.end, overlapping, config
            )
            confidence = entity.score * weight * decision.penalty
            if is_id_like(entity.text):
                confidence *= config.id_like_weight
            if priority:
                confidence += config.priority_boost
            confidence = round(min(1.0, max(0.0, confidence)), 4)

            if decision.label not in PII_TYPES:
                continue
            if decision.label == "ORG" and config.org_filter_enabled:
                if org_false_positive_reason(entity.text, config) is not None:
                    stats["org_filtered"] = stats.get("org_filtered", 0) + 1
                    continue
            candidates.append(
                Finding.from_block(
                    block,
                    entity.start,
                    entity.end,
                    decision.label,
                    "ner",
                    confidence,
                    [f"ner:{entity.backend}"],
                )
            )
    return candidates


def _accept_rule_findings(
    rule_findings: Sequence[Finding], warnings: List[str]
) -> List[Finding]:
    """Keep only rule findings that follow the contract, and say what was dropped."""
    accepted: List[Finding] = []
    dropped = 0
    for finding in rule_findings:
        if finding.pii_type not in PII_TYPES or finding.detector not in DETECTORS:
            dropped += 1
            continue
        accepted.append(finding)
    if dropped:
        warnings.append(f"Dropped {dropped} rule finding(s) that violate the Finding contract")
    return accepted


def run_p4_report(
    blocks: Sequence[TextBlock],
    rule_findings: Optional[Sequence[Finding]] = None,
    config: ConfigLike = None,
    backends: Optional[Sequence[NERBackend]] = None,
) -> P4Report:
    """Run P4 and return findings with audit information.

    Args:
        blocks: TextBlocks from one or more documents. Pass every block of a run
            in one call to get cross-file identities.
        rule_findings: P3 output, or None / [] for standalone mode.
        config: P4Config, a dict of its fields, or None for defaults.
        backends: Pre-built NER backends (tests, or reuse across runs). When None,
            backends are loaded from `config`, and load failures become warnings.

    Returns:
        P4Report. Output is deterministic for the same input and config.
    """
    cfg = config if isinstance(config, P4Config) else P4Config.from_mapping(config)
    warnings: List[str] = []
    ignored: List[Finding] = []

    if backends is None:
        backends, load_warnings = load_backends(cfg)
        warnings.extend(load_warnings)
        if not backends and (cfg.enable_spacy or cfg.enable_gliner):
            warnings.append(
                "No NER backend is available; P4 is returning rule findings only."
            )

    stats: Dict[str, int] = {}
    ner = _ner_candidates(blocks, backends, cfg, warnings, ignored, stats)

    if rule_findings:
        rules = _accept_rule_findings(rule_findings, warnings)
        evidence = [f for f in rules if f.pii_type in ("EMAIL", "EMP_ID")]
        extra_rules: List[Finding] = []
    else:
        rules = []
        evidence = extract_evidence(list(blocks))
        extra_rules = [] if cfg.defer_structured_to_rules else list(evidence)

    fused = fuse(rules + extra_rules, ner, cfg)
    final = list(fused.kept)

    identities: List[dict] = []
    conflicts: List[str] = []
    before_header = [f.pii_type for f in final]
    final = force_person_by_header(final, blocks, cfg)
    stats["header_relabelled"] = sum(1 for a, f in zip(before_header, final) if a != f.pii_type)
    if cfg.enable_linking:
        resolved = resolve_identities(final, evidence, blocks)
        before_identity = [f.pii_type for f in resolved.findings]
        relabelled = relabel_org_by_identity(resolved.findings, resolved.identities)
        stats["identity_relabelled"] = sum(1 for a, f in zip(before_identity, relabelled) if a != f.pii_type)
        if stats["identity_relabelled"]:
            resolved = resolve_identities(relabelled, evidence, blocks)
        final = resolved.findings
        identities = resolved.identities
        conflicts = resolved.conflicts

    # ORG spans still shaped the result above (fusion, relabelling); emit_org only hides them.
    if not cfg.emit_org:
        before_drop = len(final)
        final = [f for f in final if f.pii_type != "ORG"]
        stats["org_suppressed"] = before_drop - len(final)

    return P4Report(
        findings=final,
        identities=identities,
        conflicts=conflicts,
        warnings=warnings,
        backends=[b.name for b in backends],
        counts={
            "org_filtered": stats.get("org_filtered", 0),
            "header_relabelled": stats.get("header_relabelled", 0),
            "identity_relabelled": stats.get("identity_relabelled", 0),
            "org_suppressed": stats.get("org_suppressed", 0),
            "rule_input": len(rules) + len(extra_rules),
            "ner_candidates": len(ner),
            "ner_ignored": len(ignored),
            "kept": len(final),
            "below_threshold": len(fused.below_threshold),
            "absorbed": fused.absorbed,
            "identities": len(identities),
        },
        debug=list(fused.below_threshold) if cfg.emit_debug else [],
        debug_ignored=ignored if cfg.emit_debug else [],
    )


def run_p4(
    blocks: Sequence[TextBlock],
    rule_findings: Optional[Sequence[Finding]] = None,
    config: ConfigLike = None,
) -> List[Finding]:
    """Return the final PII findings for `blocks`. See `run_p4_report` for details."""
    return run_p4_report(blocks, rule_findings, config).findings
