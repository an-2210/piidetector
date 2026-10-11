"""Discovery of the P3 rule detector, so P4 can be wired in without a hard dependency.

P3 integrates in one of two ways:
  1. Call `register_rule_detector(detector)` at import time, or
  2. Expose `get_detector()` returning a `RuleDetector` from the module
     `src.pii.rules` (the package P3 owns).

If neither is present, `collect_rule_findings` returns None and P4 runs in
standalone mode.
"""

from __future__ import annotations

import importlib
import logging
from typing import List, Optional, Tuple

from src.models.text_block import TextBlock
from src.pii.contracts import Finding, RuleDetector

logger = logging.getLogger(__name__)

RULE_DETECTOR_MODULE = "src.pii.rules"

_registered: List[RuleDetector] = []


def register_rule_detector(detector: RuleDetector) -> None:
    """Register a P3 detector for the current process."""
    _registered.append(detector)


def clear_registered_detectors() -> None:
    """Remove all registered detectors (used by tests)."""
    _registered.clear()


def rule_detector_available() -> bool:
    """True when a P3 detector is registered or importable. Does not run it."""
    if _registered:
        return True
    try:
        module = importlib.import_module(RULE_DETECTOR_MODULE)
    except ImportError:
        return False
    return callable(getattr(module, "get_detector", None))


def _discover(warnings: List[str]) -> List[RuleDetector]:
    detectors: List[RuleDetector] = list(_registered)
    try:
        module = importlib.import_module(RULE_DETECTOR_MODULE)
    except ImportError:
        return detectors
    factory = getattr(module, "get_detector", None)
    if callable(factory):
        try:
            detectors.append(factory())
        except Exception as exc:  # noqa: BLE001 - P3 failure must not stop P4
            logger.exception("Could not construct P3 rule detector")
            warnings.append(f"P3 rule detector could not be created: {exc}")
    return detectors


def collect_rule_findings(
    blocks: List[TextBlock],
) -> Tuple[Optional[List[Finding]], List[str]]:
    """Run any available rule detectors over `blocks`.

    Returns:
        (findings, warnings). `findings` is None when no detector is available,
        so callers can pass it straight to `run_p4`. A detector that raises is
        skipped with a warning rather than failing the run.
    """
    warnings: List[str] = []
    detectors = _discover(warnings)
    if not detectors:
        return None, warnings

    findings: List[Finding] = []
    for detector in detectors:
        try:
            findings.extend(detector.detect(blocks))
        except Exception as exc:  # noqa: BLE001 - P3 failure must not stop P4
            logger.exception("Rule detector %r failed", detector)
            warnings.append(f"P3 rule detector failed, continuing without it: {exc}")
    return findings, warnings
