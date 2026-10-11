"""Pipeline hook: run P4 on an ExtractionResult and store the output in its metadata.

Called from `src.pipeline.extract_document` when `enable_ner=True`. Output goes
to `result.metadata["p4"]`, so the ExtractionResult and TextBlock contracts
stay unchanged. Warnings go to `result.errors`, like other recoverable issues.
"""

from __future__ import annotations

from typing import Any, Dict, Union

from src.models.text_block import ExtractionResult
from src.pii.config import P4Config
from src.pii.p4 import run_p4_report
from src.pii.registry import collect_rule_findings


def run_ner_stage(
    result: ExtractionResult,
    config: Union[P4Config, Dict[str, Any], None] = None,
) -> None:
    """Run P3 (if registered) then P4 over `result.blocks`, storing output in place."""
    cfg = P4Config.from_mapping(config)
    rule_findings, rule_warnings = collect_rule_findings(result.blocks)
    report = run_p4_report(result.blocks, rule_findings, cfg)

    result.metadata["p4"] = report.to_dict(include_debug=cfg.emit_debug)
    for message in rule_warnings + report.warnings:
        result.errors.append(f"P4 warning: {message}")
    for conflict in report.conflicts:
        result.errors.append(f"P4 identity conflict: {conflict}")
