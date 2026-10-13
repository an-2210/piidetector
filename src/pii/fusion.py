"""Fusion of rule (P3) and NER (P4) findings into one deterministic list.

Overlap rules:
  * A structured rule finding (EMAIL, PAN, ...) beats any overlapping NER span.
  * For PERSON / ORG / ADDRESS, NER beats an overlapping rule span of the same
    family. The rule's sources are kept on the NER winner as agreement.
  * Exact or overlapping duplicates of the same type merge into one Finding,
    with `sources` unioned.
  * Overlapping spans of different types: the higher-ranked candidate wins and
    the other is dropped (counted in `absorbed`).

Confidence:
  * Rule findings use the fixed `rule_confidence` from config.
  * NER findings keep the score that P4 computed upstream.
  * Each extra distinct source adds `agreement_boost`, capped at 1.0.
  * Findings below `confidence_threshold` are returned separately, so they
    appear only in debug output.

Resolution is greedy over a fixed order, so the same input always gives the
same output.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Sequence, Tuple

from src.pii.config import P4Config
from src.pii.contracts import NER_PREFERRED_TYPES, Finding


@dataclass
class FusionResult:
    """Output of `fuse`."""

    kept: List[Finding] = field(default_factory=list)
    below_threshold: List[Finding] = field(default_factory=list)
    absorbed: int = 0


def _overlaps(a: Finding, b: Finding) -> bool:
    return a.start < b.end and b.start < a.end


def _rank(finding: Finding) -> int:
    """Lower ranks win overlap contests. See the module docstring for the order.

    0  rule finding that is authoritative: P3-owned (labelled field or structured type)
    1  P4 pattern address (has a house number, cue, or city tail)
    2  NER finding for PERSON / ORG / ADDRESS
    3  rule finding for PERSON / ORG / ADDRESS without an owner claim
    4  NER finding for a structured type
    """
    if finding.detector == "rule":
        if finding.owner == "p3" or finding.pii_type not in NER_PREFERRED_TYPES:
            return 0
        return 3
    if finding.owner == "p4" and finding.pii_type == "ADDRESS":
        return 1
    return 2 if finding.pii_type in NER_PREFERRED_TYPES else 4


def _candidate_order(finding: Finding) -> Tuple:
    # Rank first, then longer spans, then the better-scored label for the same span,
    # then position and label, for a total order. Without the score term, two
    # backends that disagree on an identical span were resolved alphabetically.
    return (
        _rank(finding),
        -(finding.end - finding.start),
        -finding.confidence,
        finding.start,
        finding.pii_type,
        finding.detector,
        ",".join(sorted(finding.sources)),
    )


def _resolve_block(candidates: Sequence[Finding]) -> Tuple[List[Finding], int]:
    """Greedy overlap resolution inside one block. Returns (accepted, absorbed_count)."""
    accepted: List[Finding] = []
    absorbed = 0
    for candidate in sorted(candidates, key=_candidate_order):
        overlapping = [a for a in accepted if _overlaps(a, candidate)]
        if not overlapping:
            accepted.append(replace(candidate, sources=sorted(set(candidate.sources))))
            continue
        same_type = [a for a in overlapping if a.pii_type == candidate.pii_type]
        if len(same_type) == len(overlapping):
            target = same_type[0]
            target.sources = sorted(set(target.sources) | set(candidate.sources))
            # Agreeing candidates keep the strongest evidence, not the first one seen.
            target.confidence = max(target.confidence, candidate.confidence)
            absorbed += 1
        else:
            absorbed += 1
    return accepted, absorbed


def _score(finding: Finding, config: P4Config) -> float:
    base = config.rule_confidence if finding.detector == "rule" else finding.confidence
    extra_sources = max(0, len(set(finding.sources)) - 1)
    return min(1.0, base + config.agreement_boost * extra_sources)


def _sort_key(finding: Finding) -> Tuple:
    return (
        finding.source_file,
        finding.reading_order,
        finding.start,
        finding.end,
        finding.pii_type,
    )


def fuse(
    rule_findings: Iterable[Finding],
    ner_findings: Iterable[Finding],
    config: P4Config,
) -> FusionResult:
    """Merge rule and NER findings into the final, thresholded list.

    Args:
        rule_findings: Findings from P3 (or the internal linking extractor).
        ner_findings: NER Findings whose confidence already includes P4's
            block-weight, ambiguity and priority adjustments.
        config: Supplies rule_confidence, agreement_boost and confidence_threshold.

    Returns:
        FusionResult with `kept` (sorted, at or above threshold),
        `below_threshold` and the count of absorbed candidates.
    """
    by_block: Dict[str, List[Finding]] = {}
    for finding in list(rule_findings) + list(ner_findings):
        by_block.setdefault(finding.block_id, []).append(finding)

    result = FusionResult()
    for block_id in sorted(by_block):
        accepted, absorbed = _resolve_block(by_block[block_id])
        result.absorbed += absorbed
        for finding in accepted:
            finding.confidence = round(_score(finding, config), 4)
            if finding.confidence >= config.confidence_threshold:
                result.kept.append(finding)
            else:
                result.below_threshold.append(finding)

    result.kept.sort(key=_sort_key)
    result.below_threshold.sort(key=_sort_key)
    return result
