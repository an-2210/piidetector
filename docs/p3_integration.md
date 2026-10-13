# P3 integration: how P4 consumes the rule detectors

Written for: the P3 owner, and reviewers of the P4 pull request.

## Read this first: `owner` and the overlap policy

P4 treats rule findings by their `owner` field.

| Rule finding | Owner | Overlap with NER |
|---|---|---|
| Structured identifier (EMAIL, SSN, TIN, DOB, IDs, CARD_NUMBER, ACCOUNT_LAST4, PSEF, PASSPORT, PAN, PHONE, EMP_ID, DIR_ID, MER_IN_ID, MER_PH_ID) | `"p3"` | P3 wins over any overlapping NER span. |
| Labelled field (for example "Applicant: …", "Home address: …") | `"p3"` | P3 wins, even when NER tags the same text with a different type. |
| Address (P3's `ADDRESS`) | `None` | Unowned. P4's fuller address pattern or NER may extend it. |
| No owner | `None` | NER wins PERSON, ORG and ADDRESS overlaps. The rule's sources are kept as agreement. |

Two consequences for P3:

- **Set `owner="p3"` for any finding you are sure of.** Structured identifiers and labelled fields qualify. That is how P3's decision beats a NER guess.
- **A structural address should not claim ownership.** P3 stops at the street ("14 Harbour View Road") and leaves out the locality. Owning it would beat P4's fuller span, and scoring would then count partial spans as wrong. Measured on the sample set: unowned, P3 addresses lose to P4's full span and ADDRESS scores 100% precision and recall (overall F1 0.973). With `owner="p3"`, the partial spans win and ADDRESS falls to 11% precision and recall (overall F1 0.825).

## How P3 is connected

P3 is not modified. `src/pii/p3_adapter.py` converts P3's `Finding` (from `src/models/finding.py`) into the P4 `Finding` from `src/pii/contracts.py`:

| P3 field | P4 field |
|---|---|
| `identifier_type` | `pii_type` through `P3_TO_PII` (for example `EMP` becomes `EMP_ID`, `MER-IN` becomes `MER_IN_ID`) |
| `start_offset`, `end_offset` | `start`, `end` |
| `text_block_id` | `block_id` (P4 copies the block's location fields) |
| `confidence` | `confidence` (P4 then fixes rule confidence at `rule_confidence`, default 0.95) |
| `detector` | `detector="rule"` |
| (none) | `sources=["rule:p3"]` and `owner` as in the table above |

`INTERNAL_REF` is P3's suppression marker, not PII, so the adapter drops it.

The adapter is found automatically by `src/pii/registry.py`:

1. A `src.pii.rules` package with `get_detector()` takes precedence, if one is ever added.
2. Otherwise `src.pii.p3_adapter` is used.

It is gated by the `use_p3` flag (default `True`). Set `use_p3=False` for NER-only runs. The hook passes this flag through, so a run with `use_p3=False` contains no P3 findings.

## Safety net: ignore patterns on rule findings

P4 also drops rule findings that overlap `IGNORE_PATTERNS` (RSK-, ISS-, INC-, GRP-POL- references, policy dates, USD amounts, ratios). This is a safety net, not a replacement for P3's own suppression.

Measured on the sample set, P3 emits `2024-0031` as a PHONE inside `RSK-2024-0031` in five places. The safety net removes all five. The one remaining PHONE false positive (PESEL, gap 1) is not an ignore-pattern case. Config flag: `apply_ignore_to_rules` (default `True`).

## Gaps found in P3 on the sample set

These are in P3's code. P4 does not patch them. Each has a test or a measured case in `eval/results/eval_report.md`.

1. **PESEL is mislabelled as PHONE.** `PESEL: 80010112345` is tagged PHONE, which is the only false positive in the real-P3 run. PESEL is not a P3 type at all. Suggested fix: add a PESEL detector with its check digit, and do not let an 11-digit number fall through to the phone rule.
2. **Card last-4 is not detected.** "Card ending 4421" is missed. P3 detects `account ending 9087` as ACCOUNT_LAST4, but has no card equivalent. P4 does not duplicate this.
3. **Phone false positives from reference IDs.** The digits in `RSK-2024-0031` match the phone pattern. P4 removes them, but P3's own filter should suppress them first.
4. **Structural addresses stop before the locality.** Full-address spans come from P4's pattern, so this is currently covered. P3 could extend its span to include the city.

## Label vocabulary

`PII_TYPES` (`src/pii/contracts.py`): PERSON, ORG, ADDRESS, EMAIL, PHONE, EMP_ID, DIR_ID, MER_IN_ID, MER_PH_ID, SSN, PAN, PASSPORT, PESEL, TIN, CARD_LAST4, CARD_NUMBER, ACCOUNT_LAST4, DOB, PSEF.

- `PAN` is the Indian Permanent Account Number, as in P3. It is not a card number.
- `CARD_NUMBER` is a full card number, Luhn-validated by P3.
- `PESEL` is in the vocabulary but has no P3 detector yet (see gap 1).

## Shared false-positive controls

P3 and P4 both use `IGNORE_PATTERNS` from `src/pii/contracts.py`. Import the list rather than copying it.

## Behaviour P4 relies on

- Deterministic: the same blocks give the same findings.
- Offsets are character offsets into `TextBlock.text`, and `text[start:end]` equals the value. The adapter relies on P3's Unicode-correct offsets, which the sample set confirms.
- Table blocks keep `block.content` as rows with the header in row 0. P4 reads the header to find person columns.

To validate any rule detector's output: `src.pii.contracts.validate_finding_dict(finding.to_dict())` returns a list of problems, which is empty when valid.
