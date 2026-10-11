# P4: NER detection, fusion and entity resolution

Written for: the team deck and reviewers of the P4 pull request.

## What P4 does

P4 finds people, organisations and addresses in document text, combines them with P3's rule findings, and groups mentions of the same person. Its output is a list of `Finding` objects with stable `PERSON_n` identity IDs. P5 uses these IDs for consistent tokens such as `[PERSON_4]`.

It runs only when enabled (`enable_ner=True`). P1 and P2 are unchanged without it.

## Design

**Models.** Presidio with spaCy `en_core_web_lg` for PERSON, ORGANIZATION and LOCATION. GLiNER is optional for zero-shot labels and is not installed in the dev environment. A missing backend is a warning, not a failure.

**Addresses are a deterministic pattern, not a model output.**
- Pattern: optional unit, optional house number, 1 to 4 capitalised words, a street suffix (configurable list), optional locality, optional city, optional postcode.
- Emitted only with a house number, a cue ("address", "lives at", "registered office"), or a city tail. A bare city or a bare street name is never emitted.
- spaCy LOCATION is a place cue used only to extend a match into an adjacent place name. It is never emitted on its own. The earlier rule that mapped LOCATION to ADDRESS at half score is removed.
- Fusion gives a pattern address precedence over NER ORG on overlap. This is what stops "Broad Street" in "9 Broad Street, Lagos Island" being an organisation.

**Organisations are filtered before fusion.** Config-driven lists drop four classes of ORG false positive:
- single generic words (Audit, Finance, Legal, Risk, Compliance, HR, …),
- role phrases ("Head of X", "Director of X", "Chief … Officer"),
- governance units ("the Risk Committee", "the Lagos Operations Team"),
- PII field labels that NER tags as ORG (SSN, DOB, Email, …).

Any span with a legal suffix (Ltd, Inc, Corp, …) is never filtered.

**Person-or-organisation decisions.** Strong cues (a legal suffix or a title) relabel a span. Weak or conflicting cues lower its confidence instead of guessing. Table, OCR and identifier-like spans are down-weighted, and §16.5 and §16.8 sections are boosted.

**Relabelling, after structure is known.**
- An ORG span in a person-like table column (Name, Employee, Contact, Owner, …) becomes PERSON.
- An ORG span that exactly matches one resolved person, or is a "First Last" name compatible with exactly one identity, becomes PERSON and is linked to that identity.
- Both refuse legal suffixes and refuse ambiguous matches.

**Labelled fields from P3 are authoritative.** See the overlap policy in `docs/p3_integration.md`.

**Fusion.** Overlap order: P3-owned rule findings and structured rule findings; then P4 pattern addresses; then NER for PERSON, ORG and ADDRESS; then unowned rule findings for those types; then NER for structured types. Same-type overlaps merge with unioned sources and the best confidence. Rule findings use a fixed high confidence. Findings below the threshold appear only in debug output.

**Entity resolution.** Full names merge when surname and first name are compatible and middle initials agree. Initial-only names merge only when exactly one identity fits. Emails and EMP IDs link to a person only when that is unambiguous. An ID tied to two people is reported as a conflict, not merged. Identity numbering is deterministic.

**`emit_org` flag.** When False, ORG findings still take part in fusion and relabelling, then are removed from the output. The point is to measure what ORG contributes to disambiguation without shipping ORG labels.

## Before and after

Same 57 positive labels in every row, measured with the same harness. The decoy set grew across the rounds: the latest rows use 25 decoys (27 occurrences), the earlier rows fewer, and decoy counts are not compared here. "Before" is commit `3a1abfb`, before the address pattern.

| Stage | Mode | Overall P / R / F1 | ADDRESS P / R | ORG P | PERSON P / R |
|---|---|---|---|---|---|
| Before address pattern | NER only | 74.0 / 64.9 / 69.2 | 0 / 0 | 41.2 | 81.2 / 92.9 |
| + address pattern | NER only | 86.8 / 80.7 / 83.6 | 100 / 100 | 58.3 | 86.7 / 92.9 |
| + mock P3 and decoys | NER + mock P3 | 88.9 / 98.2 / 93.3 | 100 / 100 | 58.3 | 86.7 / 92.9 |
| + ORG filter and relabelling (this round) | NER only | 95.9 / 82.5 / 88.7 | 100 / 100 | 100.0 | 87.5 / 100 |
| + ORG filter and relabelling (this round) | NER + mock P3 | 96.6 / 100.0 / 98.3 | 100 / 100 | 100.0 | 87.5 / 100 |
| Same, `emit_org=false` | NER only | 95.2 / 70.2 / 80.8 | 100 / 100 | not emitted | 87.5 / 100 |
| Same, `emit_org=false` | NER + mock P3 | 96.2 / 87.7 / 91.7 | 100 / 100 | not emitted | 87.5 / 100 |

By source, NER + mock P3 with ORG emitted: body 97.0 / 100, table 100 / 100, slide 100 / 100, scanned OCR 83.3 / 100.

Identity (pairwise, corpus run): precision 100%, recall 100% in both NER-only and NER + mock. Before the relabelling round, recall was 94.7%.

Decoys: 0 false positives out of 27 occurrences. The earlier "Risk Committee" false positive is removed by the unit-phrase rule.

## Address recall, specifically

- Exact recall (the scoring rule, text must match): 100% at thresholds 0.1, 0.3 and 0.5.
- Overlap recall (any part found): 100% at the same thresholds.
- Before the pattern: exact recall was 0%. spaCy alone found only city or street fragments, and those scored 0.425 after the half-score rule, below the 0.5 threshold.

**Caveat.** The pattern was written with these sample addresses in view, so 100% is a ceiling on this set and not an estimate of generalisation. The memo's negatives include place names outside address context, and none produced an address. That is the only out-of-sample signal.

## Remaining misses and false positives

- **Structured identifiers in NER-only mode** (SSN, PAN, PESEL, TIN, DOB, card and account last-4, DIR, MER-IN, MER-PH): all missed. NER never emits them. The rule layer (P3) owns these; with the mock P3 they are all found.
- **PERSON false positive "Email"** (twice): spaCy tags the field label as a person. The ORG filter covers this label, but the PERSON path has no equivalent filter yet.
- **ORG with `emit_org=false`:** ORG recall falls to 0 by design. The point of the flag is to measure what ORG contributes, not to ship ORG labels.

## Limitations

- **Samples are small and self-labelled.** 57 labels from six synthetic documents, labelled by the person who wrote the pipeline. The ORG filter lists and the address pattern were chosen from failures seen in these documents. Treat the numbers as a regression baseline, not production accuracy.
- **spaCy scores are flat.** Every ORG-like span comes back at 0.85. Context rules do the separating, and they only cover the cases listed above.
- **Block IDs are random per run.** `TextBlock.block_id` is uuid4, so `Finding.block_id` changes between runs. Everything else is deterministic. Fixing this needs a P1 change.
- **Cross-file linking needs one corpus call.** The per-file hook links people within a file. Cross-file identity needs `run_p4` over all blocks together, as the eval does.
- **GLiNER is not run.** It may help with addresses, but it is untested here and it is a large dependency.
- **No real P3 yet.** The NER + real P3 mode is skipped until a P3 detector registers.

## Open decisions

1. Make `TextBlock.block_id` deterministic (for example uuid5 over source file and reading order). Needs a P1 change.
2. Keep GLiNER as an optional dependency, or drop it.
3. Confirm the §16.5 and §16.8 heading format in the case document, so the priority boost matches real headings.
4. Obtain labelled documents from real case files, so precision and recall mean something beyond this sample.
5. Decide the default for `emit_org` once P3 labelled fields cover organisations.
