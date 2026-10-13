# P4: NER detection, fusion, entity resolution, and P3 integration

## Summary

Adds P4, the stage after P1, P2 and P3. It finds people, organisations and addresses, merges them with P3's rule findings, and groups mentions of the same person into stable `PERSON_n` identities for P5.

- **Off by default.** `extract_document(..., enable_ner=True)` turns it on. P1, P2 and P3 behave as before without it.
- **Consumes P3 unchanged.** `src/pii/p3_adapter.py` converts P3's findings to the P4 contract. P3's code is not modified.
- **Deterministic.** Same input gives the same findings, identities and order. Only `Finding.block_id` varies, because P1 sets `TextBlock.block_id` to a uuid4.
- **Degrades gracefully.** A missing model, package or rule detector becomes a warning in `result.errors`.
- **Rule-based where it matters.**
  - addresses come from a deterministic street pattern,
  - ORG false positives are filtered by config-driven lists,
  - person-like ORG spans are relabelled using table headers and resolved identities.
- **Evaluation harness.** Ground-truth schema and loader, matcher, scorer, a runner with mode, GLiNER and `emit_org` switches, and a labelled synthetic set.

## Contract changes

Nothing in P1, P2 or P3 was modified by this branch. Changes to shared code:

- `src/pii/contracts.py`
  - `Finding` gains an optional `owner` field (default `None`), backward compatible.
  - `PII_TYPES` gains `CARD_NUMBER` and `PSEF`, to match P3's handoff.
  - `RuleDetector`, `IGNORE_PATTERNS` and `validate_finding_dict` were introduced earlier on this branch.
- `src/pipeline.py`: `extract_document` gains `enable_ner` (default `False`) and `ner_config`. The change is additive.
- `ExtractionResult.metadata["p4"]` is a new key. The `ExtractionResult` and `TextBlock` schemas are unchanged.
- New `P4Config` flags:
  - `use_p3` (default `True`),
  - `apply_ignore_to_rules` (default `True`),
  - `emit_org` (default `True`),
  - `enable_gliner` (default `False`).

### Overlap policy

- A rule finding with `owner="p3"` (structured identifier or labelled field) wins over NER, including NER's type.
- A P4 pattern address (`owner="p4"`) wins over NER ORG and PERSON on overlap.
- P3's structural `ADDRESS` is unowned, so P4's fuller span wins. Measured: owning it drops overall F1 from 0.973 to 0.825.
- Otherwise NER wins PERSON, ORG and ADDRESS, and the rule's sources are kept as agreement.

## How to run

```bash
pip install -r requirements.txt            # P1/P2/P3
pip install -r requirements-ner.txt        # optional: Presidio, spaCy, GLiNER
python -m spacy download en_core_web_lg    # optional: about 400 MB

python -c "from src.pipeline import extract_document; r = extract_document('case.docx', enable_ner=True); print(r.metadata['p4']['findings'])"

python eval/run_eval.py                    # all modes; add --gliner off|on|both, --emit-org true|false|both
```

## Test counts

| Environment | Result |
|---|---|
| Project venv (Presidio, spaCy `en_core_web_lg`, GLiNER, OpenCV, pytesseract) | 201 passed, 0 failed |
| System Python, no NER packages | 184 passed, 2 skipped (the model-dependent tests) |

These counts include the P3 owner's 15 detector tests and the original P1/P2 tests. In the system environment, `tests/test_ocr_pipeline.py` needs `cv2` and is excluded, as it was before this branch.

## Evaluation baseline

The eval set is 6 synthetic documents with 57 positive labels and 25 decoys (27 occurrences). GLiNER is off in this table; it scores identically when on.

| Mode | ORG emitted: P / R / F1 | ORG suppressed: P / R / F1 |
|---|---|---|
| NER only | 100.0 / 82.5 / 90.4 | 100.0 / 70.2 / 82.5 |
| **NER + real P3** | **98.2 / 96.5 / 97.3** | 98.0 / 84.2 / 90.6 |
| NER + mock P3 | 100 / 100 / 100 (circular, see below) | 100.0 / 87.7 / 93.5 |

- **Real P3, by source:** body 96.8 / 93.8, table 100 / 100, slide 100 / 100, scanned OCR 100 / 100.
- **Identity (pairwise):** precision 100%, recall 100%.
- **Decoys:** 0 false positives.
- **Remaining errors with real P3**, both on P3's side:
  - PESEL missed and mislabelled as PHONE (the one false positive),
  - card last-4 missed.

  Details are in `docs/p3_integration.md`.

**Caveat: these numbers are self-labelled.** The same author wrote P4, the samples, the labels, the ORG filter lists and the address pattern. The mock P3's 100% is circular, because its patterns were written against this ground truth. Treat everything as a regression baseline, not as accuracy on real case documents.

## Open items

1. **Deterministic `block_id`.** `TextBlock.block_id` is uuid4, so `Finding.block_id` changes per run. Fixing it needs a P1 change (for example uuid5 over source file and reading order).
2. **P3 gaps for the P3 owner:**
   - a PESEL detector (and stop 11-digit numbers falling into the phone rule),
   - card last-4,
   - suppressing the digits inside `RSK-` references (P4's safety net catches them today).
3. **GLiNER.** Installed, tested and neutral on this set, so it is opt-in. Revisit on real documents.
4. **`emit_org` default.** Left at `True`.
5. **Labelled real data.** Precision and recall should be measured on documents the pipeline's author did not write.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
