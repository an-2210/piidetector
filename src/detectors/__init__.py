"""Rule-Based Detectors module (P3).

Provides deterministic regex rules, contextual validation, false-positive suppression,
and structured Findings export feeding P4.
"""

from src.detectors.filter import FalsePositiveFilter
from src.detectors.pipeline import RuleBasedDetector, run_detectors_pipeline

__all__ = [
    "FalsePositiveFilter",
    "RuleBasedDetector",
    "run_detectors_pipeline",
]
