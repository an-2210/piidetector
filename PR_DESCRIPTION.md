# P4: NER detection, fusion and entity resolution

## Summary

Adds P4, the stage after P1 and P2 that finds people, organisations and addresses, merges them with P3 rule findings, and groups mentions of the same person into stable `PERSON_n` identities for P5.

- **Off by default.** `extract_document(..., enable_ner=True)` turns it on. P1 and P2 run unchanged without it.
- **Deterministic.** Same input gives the same findings, identities and order. Only `Finding.block_id` varies between runs, because `TextBlock.block_id` is a uuid4 set in P1.
- **Degrades gracefully.** A missing package or model becomes a warning in `result.errors`. Nothing crashes.
- **Address pattern.** Deterministic street pattern. spaCy LOCATION only extends matches.
- **ORG filter and relabelling.** Drops generic, role, governance-unit and field-label ORG false positives. Relabels person-like ORG spans to PERSON, using table headers and resolved identities.
- **Evaluation harness.** Ground-truth schema and loader, matcher, scorer, runner, and a labelled synthetic set.

## Contract changes

Nothing in P1, P2 or the P3 rule side was modified. Changes to shared code:

- `src/pii/contracts.py`: `Finding` gains an optional `owner` field (default `None`). It is backward compatible. `from_block` accepts `owner=`.
- `src/pii/contracts.py`: new `RuleDetector` protocol, `PII_TYPES`, `IGNORE_PATTERNS`, `validate_finding_dict`. (Introduced in the first commit of this branch.)
- `src/pipeline.py`: `extract_document` gains two options, `enable_ner` (default `False`) and `ner_config`. The change is additive. It is the only edit outside `src/pii`, `eval`, `tests` and `docs`.
- `ExtractionResult.metadata["p4"]` is a new key. P4 warnings go to `ExtractionResult.errors`. The `ExtractionResult` and `TextBlock` schemas are unchanged.

### Overlap policy (for P3)

- A rule finding with `owner="p3"` (labelled field or structured type) wins over NER on overlap, including NER's type.
- A P4 pattern address (`owner="p4"`) wins over NER ORG and PERSON on overlap.
- Otherwise NER wins PERSON, ORG and ADDRESS, and the rule's sources are kept as agreement.

## How to run

```bash
pip install -r requirements.txt            # P1/P2 (unchanged)
pip install -r requirements-ner.txt        # optional: Presidio, spaCy, GLiNER
python -m spacy download en_core_web_lg    # optional: about 400 MB

python -c "from src.pipeline import extract_document; r = extract_document('case.docx', enable_ner=True); print(r.metadata['p4']['findings'])"

python eval/samples/make_samples.py        # regenerate the synthetic samples (optional)
python eval/run_eval.py                    # writes eval/results/eval_report.md and eval_results.json
```

Options for `ner_config`: any `P4Config` field, for example `{"emit_org": False}`, `{"defer_structured_to_rules": False}`, or `{"enable_gliner": False}`.

## Test counts

| Environment | Result |
|---|---|
| Project venv (Presidio, spaCy `en_core_web_lg`, OpenCV, pytesseract) | 176 passed, 0 failed |
| System Python, no NER packages | 159 passed, 2 skipped (the two model-dependent tests) |

The original 30 P1/P2 tests pass in both. In the system environment, `tests/test_ocr_pipeline.py` needs `cv2` and is excluded there, as before this branch. Installing `opencv-python-headless` and `pytesseract` fixes it.

## Evaluation baseline

Measured with `eval/run_eval.py` on 6 synthetic documents: 57 positive labels and 25 decoys (27 occurrences). The modes are NER only and NER + mock P3, each with ORG emitted or suppressed.

| Mode | ORG emitted: P / R / F1 | ORG suppressed: P / R / F1 |
|---|---|---|
| NER only | 95.9 / 82.5 / 88.7 | 95.2 / 70.2 / 80.8 |
| NER + mock P3 | 96.6 / 100.0 / 98.3 | 96.2 / 87.7 / 91.7 |

Before the address pattern (commit 3a1abfb, same ground truth), NER-only overall was 74.0 / 64.9 / 69.2. ADDRESS went from 0% to 100% recall and precision. ORG precision went from 41.2% to 100%. PERSON recall went from 92.9% to 100%.

**Caveat: these samples are self-labelled.** The same person wrote the pipeline, the samples, the labels, the ORG filter lists and the address pattern. The numbers are a regression baseline. They do not estimate accuracy on real case documents. The only out-of-sample signal is the decoy memo, which has no address-shaped negatives.

Known gaps in the baseline:

- NER alone never finds structured identifiers (SSN, PAN, PESEL, TIN, DOB, card and account last-4, DIR and MER IDs). The mock P3 finds them all. A real P3 is needed.
- Two PERSON false positives, both the field label "Email" (spaCy tags it as a name).

## Open items

1. **Deterministic `block_id`.** `TextBlock.block_id` is uuid4, so `Finding.block_id` changes per run. Fixing it needs a P1 change (for example uuid5 over source file and reading order). Out of scope for this PR.
2. **GLiNER not run.** It is optional and untested in this environment. It may improve address and organisation recall.
3. **Real P3 mode.** The eval's NER + real P3 mode is skipped until a P3 detector registers (`src.pii.rules.get_detector` or `register_rule_detector`).
4. **`emit_org` default.** Left at `True`. Revisit once P3 labelled fields cover organisations.
5. **Labelled sample data.** Obtain labelled real case documents, so precision and recall are measured on data the pipeline's author did not write.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
