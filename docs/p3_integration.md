# P3 integration: emitting rule findings for P4

This page covers what the rule detector (P3) must emit so P4 can fuse it with NER. P4 needs no changes when P3 lands.

## What to emit

Return a list of `src.pii.contracts.Finding` objects from `detect(blocks)`:

| Field | Value |
| --- | --- |
| `block_id` | `TextBlock.block_id` of the block where the span was found |
| `start`, `end` | Character offsets into `block.text`, half-open. `block.text[start:end] == text` must hold |
| `text` | The matched span |
| `pii_type` | One label from `PII_TYPES` (below) |
| `detector` | `"rule"` |
| `confidence` | Any float in [0, 1]. P4 replaces rule confidence with a fixed high value (`rule_confidence`, default 0.95) |
| `sources` | e.g. `["rule:p3"]`, or the specific pattern name |
| location fields | Copy `source_file`, `source_type`, `block_type`, `source_kind`, `page_number`, `slide_number`, `section_or_heading`, `reading_order` from the block. `Finding.from_block(...)` does this for you |

`identity_id` is left as `None`. P4 sets it.

## Label vocabulary

`PII_TYPES`: PERSON, ORG, ADDRESS, EMAIL, PHONE, EMP_ID, DIR_ID, MER_IN_ID, MER_PH_ID, SSN, PAN, PASSPORT, PESEL, TIN, CARD_LAST4, ACCOUNT_LAST4, DOB.

Other labels are dropped by P4 with a warning.

**Overlap rule:** for PERSON, ORG and ADDRESS, NER wins over an overlapping rule span. Structured types (everything else) are won by the rule. Emit structured types, and leave the name-like ones to NER unless you have a strong pattern for them.

## Shared false-positive controls

Import the shared list. Don't copy it.

```python
from src.pii.contracts import IGNORE_PATTERNS, ignore_spans, overlaps_ignore

spans = ignore_spans(block.text)
if not overlaps_ignore(start, end, spans):
    findings.append(...)
```

It covers RSK-, ISS-, INC- and GRP-POL- references, policy dates, USD amounts and colon ratios. P4 applies the same list to all NER output.

## How to register the detector

Either option works. Neither needs a P4 change.

1. **Module entry point (preferred):** create `src/pii/rules/__init__.py` with a `get_detector()` function that returns an object with `detect(blocks)`. P4 discovers it automatically.
2. **Explicit registration:** at import time, call `src.pii.registry.register_rule_detector(detector)`.

If the detector raises, P4 logs a warning and continues without it.

## Behaviour P4 relies on

- Emit only EMAIL and EMP_ID as linking evidence. P4 uses them to link people across blocks and tables, and then stops using its own internal extractor.
- Be deterministic: same blocks in, same findings out.
- Don't raise on empty `block.text`.

Check your output with `src.pii.contracts.validate_finding_dict(finding.to_dict())`. It returns a list of problems, which is empty when the finding is valid.
