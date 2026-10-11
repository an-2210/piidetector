"""Evaluate P4 on the hand-labelled sample set.

Usage (from the project root, with the venv that has the NER extras):
    .venv/bin/python eval/run_eval.py                 # all available modes
    .venv/bin/python eval/run_eval.py --modes ner_only ner_mock_p3

Per-file results come from extract_document(..., enable_ner=True), which is
the production path. Identity scores come from one corpus run over every
file's blocks, because the identity groups span files and the per-file hook
cannot link across them.

Writes eval/results/eval_report.md and eval/results/eval_results.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.ground_truth import GroundTruth, load_ground_truth  # noqa: E402
from eval.metrics import build_predictions, document_text, identity_scores, match, score  # noqa: E402
from eval.mock_p3 import MockRegexP3  # noqa: E402
from src.models.text_block import TextBlock  # noqa: E402
from src.pii import registry  # noqa: E402
from src.pii.backends import SpacyPresidioBackend  # noqa: E402
from src.pii.config import P4Config  # noqa: E402
from src.pii.contracts import Finding  # noqa: E402
from src.pii.p4 import run_p4_report  # noqa: E402
from src.pipeline import extract_document  # noqa: E402

SAMPLES = ROOT / "eval" / "samples"
RESULTS = ROOT / "eval" / "results"
MODES = ("ner_only", "ner_mock_p3", "ner_real_p3")
MODE_TITLES = {
    "ner_only": "NER only (standalone; Presidio structured recognisers and internal extractor on)",
    "ner_mock_p3": "NER + mock P3 (regex EMAIL/EMP_ID as rule findings; defer on)",
    "ner_real_p3": "NER + real P3 (registered detector)",
}
ADDRESS_THRESHOLDS = (0.5, 0.3, 0.1)


def _mode_config(mode: str) -> Dict:
    if mode == "ner_only":
        return {"defer_structured_to_rules": False}
    return {"defer_structured_to_rules": True}


def _apply_mode(mode: str) -> Optional[str]:
    """Set the P3 registry for this mode. Returns a skip reason, or None if the mode can run."""
    registry.clear_registered_detectors()
    if mode == "ner_mock_p3":
        registry.register_rule_detector(MockRegexP3())
    if mode == "ner_real_p3" and not registry.rule_detector_available():
        return "no P3 rule detector registered or importable (src.pii.rules.get_detector)"
    return None


def _uses_rules(mode: str) -> bool:
    return mode != "ner_only"


def _finding_row(prediction) -> Dict:
    f = prediction.finding
    return {
        "file": f.source_file,
        "location": prediction.location,
        "source_kind": f.source_kind,
        "pii_type": f.pii_type,
        "text": f.text,
        "confidence": f.confidence,
        "sources": f.sources,
    }


def run_mode(mode: str, truth: GroundTruth, sample_dir: Path) -> Dict:
    reason = _apply_mode(mode)
    if reason:
        return {"mode": mode, "status": "skipped", "reason": reason}

    cfg = {**_mode_config(mode), "emit_debug": False}
    per_file = {}
    warnings: List[str] = []
    for file in truth.files:
        per_file[file] = extract_document(sample_dir / file, enable_ocr=True, enable_ner=True, ner_config=cfg)
        warnings.extend(f"{file}: {e}" for e in per_file[file].errors)

    blocks = [b for result in per_file.values() for b in result.blocks]
    backends = next(
        (result.metadata["p4"]["backends"] for result in per_file.values() if "p4" in result.metadata),
        [],
    )
    per_file_findings: List[Finding] = []
    for result in per_file.values():
        per_file_findings += [Finding.from_dict(d) for d in result.metadata.get("p4", {}).get("findings", [])]

    doc_preds = build_predictions(per_file_findings, blocks)
    doc_match = match(truth.labels, doc_preds)
    doc_score = score(truth, doc_preds, doc_match, blocks)

    rule_findings = None
    if _uses_rules(mode):
        rule_findings, _ = registry.collect_rule_findings(blocks)
    corpus = run_p4_report(blocks, rule_findings, cfg)
    corpus_preds = build_predictions(corpus.findings, blocks)
    corpus_match = match(truth.labels, corpus_preds)
    identity = identity_scores(corpus_match, corpus_preds)

    misses = [
        {"file": g.file, "location": g.page, "source_kind": g.source_kind, "pii_type": g.pii_type, "text": g.text}
        for g in doc_match.missed
    ]
    false_positives = [_finding_row(p) for p in doc_match.unmatched]

    return {
        "mode": mode,
        "status": "ran",
        "title": MODE_TITLES[mode],
        "config": cfg,
        "backends": backends,
        "warnings": warnings + corpus.warnings,
        "scores": doc_score,
        "identity": identity,
        "misses": misses,
        "false_positives": false_positives,
    }


def address_diagnostics(truth: GroundTruth, sample_dir: Path) -> Dict:
    """How ADDRESS behaves when spaCy is the only NER source, and where it misses.

    Two recall figures per threshold:
      * exact: the predicted span has the same normalised text as the label (the scoring rule),
      * overlap: any predicted ADDRESS span overlaps the label's characters. This shows
        whether spaCy finds part of the address even when the full address is missed.
    """
    blocks: List[TextBlock] = []
    for file in truth.files:
        blocks += extract_document(sample_dir / file, enable_ocr=True).blocks

    registry.clear_registered_detectors()
    low = run_p4_report(blocks, None, {"defer_structured_to_rules": False, "confidence_threshold": 0.1})
    candidates = build_predictions(low.findings, blocks)
    addresses_truth = [g for g in truth.labels if g.pii_type == "ADDRESS"]

    def label_span(label) -> Optional[tuple]:
        text = document_text(blocks, label.file, label.page)
        index = text.find(label.text)
        return (index, index + len(label.text)) if index >= 0 else None

    gt_spans = {id(g): label_span(g) for g in addresses_truth}

    by_threshold = {}
    for threshold in ADDRESS_THRESHOLDS:
        kept = [p for p in candidates if p.finding.confidence >= threshold and p.finding.pii_type == "ADDRESS"]
        outcome = match(addresses_truth, kept)
        overlapped = sum(
            1
            for g in addresses_truth
            if gt_spans[id(g)] and any(
                p.file == g.file and p.location == g.page and p.span
                and p.span[0] < gt_spans[id(g)][1] and gt_spans[id(g)][0] < p.span[1]
                for p in kept
            )
        )
        by_threshold[str(threshold)] = {
            "exact_recall": len(outcome.pairs) / len(addresses_truth) if addresses_truth else None,
            "overlap_recall": overlapped / len(addresses_truth) if addresses_truth else None,
            "exact_precision": len(outcome.pairs) / len(kept) if kept else None,
            "matched": len(outcome.pairs),
            "overlapped": overlapped,
            "predicted": len(kept),
            "truth": len(addresses_truth),
        }

    spacy = SpacyPresidioBackend(P4Config(defer_structured_to_rules=True))
    raw_by_block = {b.block_id: spacy.predict(b.text or "") for b in blocks}
    at_default = match(
        addresses_truth,
        [p for p in candidates if p.finding.confidence >= 0.5 and p.finding.pii_type == "ADDRESS"],
    )
    misses = []
    for label in at_default.missed:
        block = next(
            (b for b in blocks if b.source_file == label.file and label.text in (b.text or "")),
            None,
        )
        raw_hits = []
        if block is not None:
            start = block.text.find(label.text)
            for raw in raw_by_block.get(block.block_id, []):
                if raw.start < start + len(label.text) and start < raw.end:
                    raw_hits.append({"text": raw.text, "label": raw.label, "raw_score": round(raw.score, 4)})
        span = gt_spans[id(label)]
        nearby = [
            {"text": p.finding.text, "pii_type": p.finding.pii_type, "confidence": round(p.finding.confidence, 4)}
            for p in candidates
            if p.file == label.file and span and p.span and p.span[0] < span[1] and span[0] < p.span[1]
        ]
        misses.append({
            "file": label.file,
            "source_kind": label.source_kind,
            "text": label.text,
            "spacy_spans_overlapping": raw_hits,
            "fused_candidates_overlapping": nearby,
        })

    raw_address_spans = [
        {"file": b.source_file, "text": raw.text, "raw_score": round(raw.score, 4)}
        for b in blocks
        for raw in raw_by_block.get(b.block_id, [])
        if raw.label == "ADDRESS"
    ]
    return {
        "by_threshold": by_threshold,
        "truth": len(addresses_truth),
        "misses_at_default": misses,
        "spacy_address_spans": raw_address_spans,
    }


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _prf_row(name: str, stats: Dict) -> str:
    return f"| {name} | {stats['tp']} | {stats['fp']} | {stats['fn']} | {_pct(stats['precision'])} | {_pct(stats['recall'])} | {_pct(stats['f1'])} |"


def render_markdown(modes: List[Dict], address: Optional[Dict], truth: GroundTruth) -> str:
    lines = [
        "# P4 evaluation report",
        "",
        f"Ground truth: {len(truth.labels)} labels, {len(truth.decoys)} decoys, {len(truth.files)} files.",
        "Matching: file + location + pii_type + normalised text; when a label has a span, IoU >= 0.5. "
        "Never uses block_id.",
        "",
    ]
    for mode in modes:
        lines.append(f"## {MODE_TITLES.get(mode['mode'], mode['mode'])}")
        lines.append("")
        if mode["status"] == "skipped":
            lines += [f"**Skipped:** {mode['reason']}", ""]
            continue
        s = mode["scores"]
        o = s["overall"]
        lines += [
            f"Backends: {', '.join(mode['backends']) or 'none'}. Overall: P {_pct(o['precision'])}, "
            f"R {_pct(o['recall'])}, F1 {_pct(o['f1'])} (TP {o['tp']}, FP {o['fp']}, FN {o['fn']}).",
            "",
            "### By PII type",
            "",
            "| Type | TP | FP | FN | Precision | Recall | F1 |",
            "|---|---|---|---|---|---|---|",
        ]
        lines += [_prf_row(t, st) for t, st in s["per_type"].items()]
        lines += ["", "### By source type", "", "| Source | TP | FP | FN | Precision | Recall | F1 |", "|---|---|---|---|---|---|---|"]
        lines += [_prf_row(k, st) for k, st in s["per_source"].items()]
        ident = mode["identity"]
        lines += [
            "",
            f"Decoy false positives: {s['decoy_false_positives']} (of {sum(k['occurrences'] for k in s['decoy_by_kind'].values())} decoy occurrences).",
            "",
        ]
        if s["decoy_by_kind"]:
            lines += ["| Decoy category | Decoys | Occurrences | False positives |", "|---|---|---|---|"]
            lines += [f"| {k} | {v['decoys']} | {v['occurrences']} | {v['false_positives']} |" for k, v in s["decoy_by_kind"].items()]
            lines.append("")
        if s["decoy_text_not_found"]:
            lines += ["Decoy text not found in the document (fix the ground truth): " + "; ".join(s["decoy_text_not_found"]), ""]
        lines += [
            f"Identity (pairwise, PERSON, corpus run): precision {_pct(ident['precision'])} "
            f"({ident['correct_pred_pairs']}/{ident['pred_pairs']} predicted pairs correct), "
            f"recall {_pct(ident['recall'])} ({ident['linked_truth_pairs']}/{ident['truth_pairs']} truth pairs linked).",
            "",
        ]
        if mode["warnings"]:
            lines += ["Warnings: " + "; ".join(sorted(set(mode["warnings"]))), ""]
        if mode["misses"]:
            lines += ["<details><summary>Missed labels</summary>", ""]
            lines += [f"- {m['file']} p{m['location'] or '-'} [{m['source_kind']}] {m['pii_type']}: {m['text']!r}" for m in mode["misses"]]
            lines += ["", "</details>", ""]
        if mode["false_positives"]:
            lines += ["<details><summary>False positives</summary>", ""]
            lines += [f"- {fp['file']} [{fp['source_kind']}] {fp['pii_type']}: {fp['text']!r} (conf {fp['confidence']})" for fp in mode["false_positives"]]
            lines += ["", "</details>", ""]

    if address is not None:
        lines += ["## ADDRESS diagnostics (spaCy only)", ""]
        lines.append(
            "How ADDRESS is found: a deterministic street pattern (house number, capitalised name, street suffix, "
            "optional locality and city; see src/pii/address.py), with spaCy LOCATION spans used only to extend "
            "a match. spaCy LOCATION is never emitted as ADDRESS on its own. The rows below sweep the confidence "
            "threshold over the same candidates."
        )
        lines += ["", "| Threshold | Exact recall (scoring rule) | Overlap recall (any part found) | Matched | Overlapped | Predicted | Truth | Exact precision |", "|---|---|---|---|---|---|---|---|"]
        for threshold, row in address["by_threshold"].items():
            lines.append(
                f"| {threshold} | {_pct(row['exact_recall'])} | {_pct(row['overlap_recall'])} | {row['matched']} | "
                f"{row['overlapped']} | {row['predicted']} | {row['truth']} | {_pct(row['exact_precision'])} |"
            )
        lines += ["", f"Misses at the default threshold (0.5), out of {address['truth']} ADDRESS labels (empty means none):", ""]
        for miss in address["misses_at_default"]:
            spacy = (
                "; ".join(f"{h['text']!r} label {h['label']} raw {h['raw_score']}" for h in miss["spacy_spans_overlapping"])
                or "no spaCy span overlapping this text"
            )
            fused = "; ".join(f"{c['text']!r} {c['pii_type']} conf {c['confidence']}" for c in miss["fused_candidates_overlapping"]) or "none"
            lines.append(f"- {miss['file']} [{miss['source_kind']}] {miss['text']!r}: spaCy: {spacy}. Fused candidates: {fused}.")
        lines += ["", "Raw spaCy ADDRESS (LOCATION) spans found anywhere:", ""]
        lines += [f"- {r['file']}: {r['text']!r} raw {r['raw_score']}" for r in address["spacy_address_spans"]] or ["- none"]
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate P4 on the hand-labelled samples.")
    parser.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    parser.add_argument("--ground-truth", type=Path, default=SAMPLES / "ground_truth.json")
    parser.add_argument("--samples", type=Path, default=SAMPLES)
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    truth = load_ground_truth(args.ground_truth)
    missing = [f for f in truth.files if not (args.samples / f).exists()]
    if missing:
        print(f"Missing sample files: {missing}", file=sys.stderr)
        return 2

    modes = [run_mode(mode, truth, args.samples) for mode in args.modes]
    address = address_diagnostics(truth, args.samples) if "ner_only" in args.modes else None
    registry.clear_registered_detectors()

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "eval_results.json").write_text(
        json.dumps({"modes": modes, "address": address}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (args.out / "eval_report.md").write_text(render_markdown(modes, address, truth), encoding="utf-8")
    for mode in modes:
        if mode["status"] == "ran":
            o = mode["scores"]["overall"]
            print(f"{mode['mode']:<12} P={_pct(o['precision'])} R={_pct(o['recall'])} F1={_pct(o['f1'])}")
        else:
            print(f"{mode['mode']:<12} skipped: {mode['reason']}")
    print(f"wrote {args.out / 'eval_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
