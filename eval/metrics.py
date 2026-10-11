"""Matching and scoring for P4 evaluation.

Matching never uses `block_id`, which is a uuid4 that changes every run.
A prediction matches a ground-truth label when all of these agree:
  * file name,
  * location (PDF page or PPTX slide; None for DOCX),
  * pii_type,
  * normalised text,
  * and, when the label has a span, IoU >= 0.5 of the spans.

Spans are measured in "document coordinates": the blocks of one (file, location)
joined with "\n" in reading order. This is stable across runs even though
block ids are not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.models.text_block import TextBlock
from src.pii.contracts import Finding
from eval.ground_truth import GTLabel, GroundTruth

SPAN_IOU_THRESHOLD = 0.5
_TITLE = re.compile(r"^(?:dr|mr|mrs|ms|miss|prof)\.?\s+", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w@]+")


def normalize_text(text: str) -> str:
    """Lowercase, drop leading honorifics, and treat punctuation as a space.

    "Dr. Priya Raman" and "priya raman" both normalise to "priya raman";
    "M. T. Achebe" to "m t achebe".
    """
    value = _TITLE.sub("", text.strip().casefold())
    return " ".join(_NON_WORD.sub(" ", value).split())


def location_of_block(block: TextBlock) -> Optional[int]:
    if block.page_number is not None:
        return block.page_number
    return block.slide_number


def location_of_finding(finding: Finding) -> Optional[int]:
    if finding.page_number is not None:
        return finding.page_number
    return finding.slide_number


def document_offsets(blocks: Iterable[TextBlock]) -> Dict[str, Tuple[Tuple[str, Optional[int]], int]]:
    """Map block_id -> ((file, location), base offset) in document coordinates."""
    groups: Dict[Tuple[str, Optional[int]], List[TextBlock]] = {}
    for block in blocks:
        groups.setdefault((block.source_file, location_of_block(block)), []).append(block)
    bases: Dict[str, Tuple[Tuple[str, Optional[int]], int]] = {}
    for key, members in groups.items():
        offset = 0
        for block in sorted(members, key=lambda b: (b.reading_order, b.block_id)):
            bases[block.block_id] = (key, offset)
            offset += len(block.text or "") + 1  # +1 for the joining newline
    return bases


def document_text(blocks: Iterable[TextBlock], file: str, location: Optional[int]) -> str:
    """Joined text of one (file, location), in the coordinates used for spans."""
    members = [b for b in blocks if b.source_file == file and location_of_block(b) == location]
    return "\n".join(b.text or "" for b in sorted(members, key=lambda b: (b.reading_order, b.block_id)))


def decoy_occurrences(text: str, decoy_text: str) -> List[Tuple[int, int]]:
    """All case-insensitive occurrences of `decoy_text` in `text`, as [start, end)."""
    needle = decoy_text.casefold()
    haystack = text.casefold()
    found: List[Tuple[int, int]] = []
    index = haystack.find(needle)
    while index >= 0:
        found.append((index, index + len(needle)))
        index = haystack.find(needle, index + 1)
    return found


def document_span(finding: Finding, bases: Dict[str, Tuple[Tuple[str, Optional[int]], int]]) -> Optional[Tuple[int, int]]:
    entry = bases.get(finding.block_id)
    if entry is None:
        return None
    _, base = entry
    return (base + finding.start, base + finding.end)


def span_iou(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    inter = max(0, min(a[1], b[1]) - max(a[0], b[0]))
    union = (a[1] - a[0]) + (b[1] - b[0]) - inter
    return inter / union if union > 0 else 0.0


@dataclass
class Prediction:
    """A Finding plus the document-coordinate data scoring needs."""

    finding: Finding
    file: str
    location: Optional[int]
    norm: str
    span: Optional[Tuple[int, int]]


def build_predictions(findings: Sequence[Finding], blocks: Sequence[TextBlock]) -> List[Prediction]:
    bases = document_offsets(blocks)
    return [
        Prediction(
            finding=f,
            file=f.source_file,
            location=location_of_finding(f),
            norm=normalize_text(f.text),
            span=document_span(f, bases),
        )
        for f in findings
    ]


def _label_matches(label: GTLabel, pred: Prediction) -> bool:
    if (label.file, label.page, label.pii_type) != (pred.file, pred.location, pred.finding.pii_type):
        return False
    if normalize_text(label.text) != pred.norm:
        return False
    if label.span is not None:
        return pred.span is not None and span_iou(label.span, pred.span) >= SPAN_IOU_THRESHOLD
    return True


@dataclass
class MatchResult:
    """One-to-one matching between ground truth and predictions."""

    pairs: List[Tuple[GTLabel, Prediction]] = field(default_factory=list)
    missed: List[GTLabel] = field(default_factory=list)
    unmatched: List[Prediction] = field(default_factory=list)


def match(truth: Sequence[GTLabel], predictions: Sequence[Prediction]) -> MatchResult:
    """Greedy one-to-one match. Each label takes its most confident compatible prediction.

    Labels are processed in file order, so the result does not depend on the
    order predictions were produced in.
    """
    used: set = set()
    result = MatchResult()
    order = sorted(range(len(predictions)), key=lambda i: (-predictions[i].finding.confidence, i))
    for label in sorted(truth, key=lambda g: (g.file, g.page or 0, g.text, g.pii_type)):
        chosen = None
        for index in order:
            if index in used:
                continue
            if _label_matches(label, predictions[index]):
                chosen = index
                break
        if chosen is None:
            result.missed.append(label)
        else:
            used.add(chosen)
            result.pairs.append((label, predictions[chosen]))
    result.unmatched = [p for i, p in enumerate(predictions) if i not in used]
    return result


def prf(tp: int, fp: int, fn: int) -> Dict[str, Optional[float]]:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if precision is None or recall is None or precision + recall == 0:
        f1 = 0.0 if (precision is not None and recall is not None) else None
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def score(
    truth: GroundTruth,
    predictions: Sequence[Prediction],
    result: MatchResult,
    blocks: Sequence[TextBlock] = (),
) -> Dict:
    """Per-type, per-source, overall, decoy and identity scores for one run."""
    from src.pii.contracts import PII_TYPES

    per_type: Dict[str, Dict] = {}
    for t in PII_TYPES:
        tp = sum(1 for g, _ in result.pairs if g.pii_type == t)
        fn = sum(1 for g in result.missed if g.pii_type == t)
        fp = sum(1 for p in result.unmatched if p.finding.pii_type == t)
        if tp + fp + fn:
            per_type[t] = prf(tp, fp, fn)

    per_source: Dict[str, Dict] = {}
    for kind in ("body", "table", "slide", "image_ocr"):
        tp = sum(1 for g, _ in result.pairs if g.source_kind == kind)
        fn = sum(1 for g in result.missed if g.source_kind == kind)
        fp = sum(1 for p in result.unmatched if p.finding.source_kind == kind)
        if tp + fp + fn:
            per_source[kind] = prf(tp, fp, fn)

    overall = prf(
        len(result.pairs),
        len(result.unmatched),
        len(result.missed),
    )

    decoy_hits, decoy_stats, not_found = decoy_scores(truth, predictions, blocks)

    return {
        "overall": overall,
        "per_type": per_type,
        "per_source": per_source,
        "decoy_false_positives": len({id(h["pred"]) for h in decoy_hits}),
        "decoy_by_kind": decoy_stats,
        "decoy_hits": [{k: v for k, v in h.items() if k != "pred"} | {"pred_text": h["pred"].finding.text} for h in decoy_hits],
        "decoy_text_not_found": not_found,
        "identity": identity_scores(result, predictions),
    }


def decoy_scores(truth: GroundTruth, predictions: Sequence[Prediction], blocks: Sequence[TextBlock]):
    """A prediction is a decoy false positive when its span overlaps a decoy occurrence.

    If a decoy sets `not_type`, only predictions of that type count. Returns
    (hits, per-kind stats, decoys whose text was not found in the document).
    """
    hits: List[Dict] = []
    stats: Dict[str, Dict[str, int]] = {}
    not_found: List[str] = []
    for decoy in truth.decoys:
        kind = stats.setdefault(decoy.kind, {"decoys": 0, "occurrences": 0, "false_positives": 0})
        kind["decoys"] += 1
        text = document_text(blocks, decoy.file, decoy.page)
        occurrences = decoy_occurrences(text, decoy.text)
        if not occurrences:
            not_found.append(f"{decoy.file} p{decoy.page or '-'}: {decoy.text!r}")
            continue
        kind["occurrences"] += len(occurrences)
        for pred in predictions:
            if pred.file != decoy.file or pred.location != decoy.page or pred.span is None:
                continue
            if decoy.not_type is not None and pred.finding.pii_type != decoy.not_type:
                continue
            if any(pred.span[0] < end and start < pred.span[1] for start, end in occurrences):
                hits.append({"decoy": decoy.text, "kind": decoy.kind, "pred": pred})
                kind["false_positives"] += 1
    return hits, stats, not_found


def identity_scores(result: MatchResult, predictions: Sequence[Prediction]) -> Dict:
    """Pairwise precision and recall of identity grouping over PERSON mentions.

    Truth pairs: every pair of ground-truth PERSON labels in the same identity
    group, including labels the matcher missed (an unmatched mention cannot be
    linked, so it costs recall).
    Predicted pairs: every pair of predicted PERSON findings sharing an
    identity_id. A predicted pair is correct when both findings matched labels
    in the same group. A truth pair is linked when both labels matched and the
    predictions share an identity_id.
    """
    truth = [g for g, _ in result.pairs if g.pii_type == "PERSON" and g.identity] + [
        g for g in result.missed if g.pii_type == "PERSON" and g.identity
    ]
    matched_pred = {id(g): p for g, p in result.pairs}

    truth_pairs = linked = 0
    for i in range(len(truth)):
        for j in range(i + 1, len(truth)):
            if truth[i].identity != truth[j].identity:
                continue
            truth_pairs += 1
            pa, pb = matched_pred.get(id(truth[i])), matched_pred.get(id(truth[j]))
            if pa and pb and pa.finding.identity_id is not None and pa.finding.identity_id == pb.finding.identity_id:
                linked += 1

    label_of_pred = {id(p): g for g, p in result.pairs}
    persons = [p for p in predictions if p.finding.pii_type == "PERSON" and p.finding.identity_id]
    pred_pairs = correct = 0
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            a, b = persons[i], persons[j]
            if a.finding.identity_id != b.finding.identity_id:
                continue
            pred_pairs += 1
            ga, gb = label_of_pred.get(id(a)), label_of_pred.get(id(b))
            if ga and gb and ga.identity and ga.identity == gb.identity:
                correct += 1

    return {
        "pred_pairs": pred_pairs,
        "correct_pred_pairs": correct,
        "truth_pairs": truth_pairs,
        "linked_truth_pairs": linked,
        "precision": correct / pred_pairs if pred_pairs else None,
        "recall": linked / truth_pairs if truth_pairs else None,
    }
