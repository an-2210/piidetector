# P3 integration: emitting rule findings for P4

Written for: the P3 owner.

## Read this first: `owner` and the overlap policy

Every rule finding should set `owner="p3"`. The field tells P4 that P3 is authoritative for that span.

| Your finding | Set | Overlap result against NER |
|---|---|---|
| Labelled field ("Applicant: …", "Home address: …", "Employee: …") | `owner="p3"` | Your span wins, even when NER tags the same text with a different type. A labelled PERSON beats a spaCy ORG on the same span. |
| Structured type (EMAIL, SSN, PAN, DOB, IDs, …) | `owner="p3"` | Your span wins over any overlapping NER span. |
| Anything else, or no owner | `None` | NER wins PERSON, ORG and ADDRESS overlaps. Your sources are kept as agreement. |

Three consequences:

- **P4 owns addresses without a P3 claim.** P4's pattern addresses have `owner="p4"`. They fill prose gaps only. If you emit ADDRESS for a labelled field, P4 does not override it.
- **Emit a labelled field only when the label is explicit.** A bare name without a label is left to NER.
- **Emit exact duplicates freely.** Two patterns matching the same span merge into one finding with both sources.

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
| `owner` | `"p3"` (see above) |
| location fields | Copy `source_file`, `source_type`, `block_type`, `source_kind`, `page_number`, `slide_number`, `section_or_heading`, `reading_order` from the block. `Finding.from_block(...)` does this for you |

`identity_id` is left as `None`. P4 sets it.

## Label vocabulary

`PII_TYPES`: PERSON, ORG, ADDRESS, EMAIL, PHONE, EMP_ID, DIR_ID, MER_IN_ID, MER_PH_ID, SSN, PAN, PASSPORT, PESEL, TIN, CARD_LAST4, ACCOUNT_LAST4, DOB.

Other labels are dropped by P4 with a warning. P4 does not emit ORG for field labels or generic words; those are filtered before fusion, so P3 should not emit them as ORG either.

## Shared false-positive controls

Import the shared list. Don't copy it.

```python
from src.pii.contracts import IGNORE_PATTERNS, ignore_spans, overlaps_ignore

spans = ignore_spans(block.text)
if not overlaps_ignore(start, end, spans):
    findings.append(...)
```

It covers RSK-, ISS-, INC- and GRP-POL- references, policy dates, USD amounts and colon ratios. P4 applies the same list to all NER and pattern output.

## How to register the detector

Either option works. Neither needs a P4 change.

1. **Module entry point (preferred):** create `src/pii/rules/__init__.py` with a `get_detector()` function that returns an object with `detect(blocks)`. P4 discovers it automatically.
2. **Explicit registration:** at import time, call `src.pii.registry.register_rule_detector(detector)`.

If the detector raises, P4 logs a warning and continues without it.

## Behaviour P4 relies on

- Emit EMAIL and EMP_ID as linking evidence. P4 uses them to link people across blocks and tables. Once you emit them, P4 stops using its own internal extractor.
- Be deterministic: same blocks in, same findings out.
- Don't raise on empty `block.text`.
- For table blocks, keep `block.content` as the row list with the header in row 0. P4 uses the header to find person columns.

Check your output with `src.pii.contracts.validate_finding_dict(finding.to_dict())`. It returns a list of problems, which is empty when the finding is valid.

A reference implementation that exercises every rule above is `eval/mock_p3.py`.
