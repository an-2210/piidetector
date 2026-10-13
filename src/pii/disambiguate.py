"""Person vs organisation disambiguation for NER spans.

Evidence comes from the span text and the words immediately around it:

* Strong cues: an org suffix (Ltd, Inc, LLC, GmbH, ...) or a person title
  (Mr, Ms, Dr, ...). A strong cue that contradicts the model label relabels
  the span, because the surface form is unambiguous.
* Weak cues: words such as "vendor", "client" or "at" (org) and "employee",
  "analyst" or "CEO" (person). A weak cue that contradicts the label is
  ambiguous, so the label is kept and confidence is reduced.
* Backend disagreement: when backends disagree on PERSON vs ORG, the span is
  ambiguous too.

P4 never guesses without evidence. Ambiguity lowers confidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Set

from src.pii.config import P4Config

# Legal-form suffixes only. Common nouns such as "Group" or "Bank" are left out
# because they appear in ordinary prose and would mislabel people.
ORG_SUFFIX = re.compile(
    r"\b(?:Ltd|Limited|Inc|LLC|LLP|Pvt|Private|GmbH|Corp|Corporation|PLC|Plc)\b\.?",
)
PERSON_TITLE = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s+", re.IGNORECASE)
TITLE_BEFORE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof)\.?\s*$", re.IGNORECASE)
ORG_CONTEXT = re.compile(
    r"\b(?:at|vendor|client|supplier|partner|company|firm|from)\s*$", re.IGNORECASE
)
PERSON_CONTEXT = re.compile(
    r"\b(?:employee|staff|analyst|manager|officer|contact|CEO|CFO|CISO|director|lead)"
    r"\s*[:\-]?\s*$",
    re.IGNORECASE,
)
_AFTER_WINDOW = 12
_BEFORE_WINDOW = 40


@dataclass(frozen=True)
class LabelDecision:
    """Outcome of disambiguating one span."""

    label: str
    penalty: float  # multiplier on confidence, 1.0 = no penalty
    reason: str  # short tag for debug output


def _strong_cue(text: str, after: str, before: str) -> Optional[str]:
    if ORG_SUFFIX.search(text) or ORG_SUFFIX.match(after.lstrip()):
        return "ORG"
    if PERSON_TITLE.match(text) or TITLE_BEFORE.search(before):
        return "PERSON"
    return None


def _weak_cue(before: str) -> Optional[str]:
    if ORG_CONTEXT.search(before):
        return "ORG"
    if PERSON_CONTEXT.search(before):
        return "PERSON"
    return None


def decide_label(
    text: str,
    label: str,
    block_text: str,
    start: int,
    end: int,
    backend_labels: Set[str],
    config: P4Config,
) -> LabelDecision:
    """Pick the final PERSON/ORG label for a span and how much to trust it.

    Args:
        text: The span text.
        label: The label the backend proposed.
        block_text: Full text of the block (for context).
        start, end: Span offsets within `block_text`.
        backend_labels: All labels any backend proposed for this exact span.
        config: P4 config (supplies the ambiguity penalty).

    Non-PERSON/ORG labels pass through unchanged with no penalty.
    """
    if label not in ("PERSON", "ORG"):
        return LabelDecision(label, 1.0, "not_person_or_org")

    before = block_text[max(0, start - _BEFORE_WINDOW) : start]
    after = block_text[end : end + _AFTER_WINDOW]

    strong = _strong_cue(text, after, before)
    if strong is not None and strong != label:
        return LabelDecision(strong, 1.0, "strong_cue_relabel")

    disagreement = len(backend_labels & {"PERSON", "ORG"}) > 1
    weak = _weak_cue(before)
    if weak is not None and weak != label:
        return LabelDecision(label, config.ambiguity_penalty, "weak_cue_conflict")
    if disagreement:
        return LabelDecision(label, config.ambiguity_penalty, "backend_disagreement")
    return LabelDecision(label, 1.0, "agreed_or_no_conflict")


def org_false_positive_reason(text: str, config: P4Config) -> Optional[str]:
    """Why an ORG span is not an organisation, or None if it may be one.

    Categories (lists live in P4Config):
      generic_word     a single common word: Audit, Finance, Legal, Risk, ...
      role_phrase      a job or role: "Head of Audit", "Chief Risk Officer"
      unit_phrase      "the <words> Committee|Board|Department|Team|...", a governance body
      pii_field_label  a field label that NER tags as ORG: SSN, Email, DOB, ...
    A span with a legal suffix is never treated as a false positive here.
    """
    value = text.strip()
    if not value or ORG_SUFFIX.search(value):
        return None
    lowered = value.casefold()
    generic = {w.casefold() for w in config.org_generic_words}
    if lowered in generic:
        return "generic_word"
    tokens = re.findall(r"[A-Za-z]+", value)
    connectors = {"and", "or", "&"}
    if len(tokens) > 1 and all(t.casefold() in generic or t.casefold() in connectors for t in tokens):
        return "generic_word"
    if lowered in {w.casefold() for w in config.pii_field_labels}:
        return "pii_field_label"
    for pattern in config.org_role_patterns:
        if re.search(pattern, value, re.IGNORECASE):
            return "role_phrase"
    if re.match(config.org_unit_pattern, value, re.IGNORECASE):
        return "unit_phrase"
    return None
