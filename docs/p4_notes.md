# P4: NER detection, fusion and entity resolution

## What P4 does

P4 finds people, organisations and addresses in the document text, combines them with rule-based findings from P3, and groups mentions that refer to the same person. The output is a list of `Finding` objects with stable `PERSON_n` identity IDs, which P5 uses for consistent tokens such as `[PERSON_4]`.

It runs only when enabled (`enable_ner=True`). P1 and P2 run unchanged without it.

## Prose detection

- **Models.** Presidio with spaCy `en_core_web_lg` (the transformer model is a config switch). GLiNER is optional for zero-shot person, address and organisation labels. Each backend is optional. A missing model produces a warning, not a failure.
- **Weighting by where the text sits.** Body prose is trusted most (1.0). Slides get 0.9, OCR text 0.8, and table cells 0.8. Tables were originally at 0.5, which dropped almost every roster name below threshold on a real run, so they were raised to 0.8. Identifier-looking tokens (for example `EMP-40123`) get an additional 0.5 multiplier.
- **Priority sections.** Findings under headings containing §16.5 or §16.8 get a +0.05 boost. This is a heuristic on the heading text and has not been checked against the actual case document, which is not in the repository.
- **Structured types.** With `defer_structured_to_rules=True` (default), Presidio runs only its PERSON, ORGANIZATION and LOCATION recognisers. Email, phone, SSN and card detection stay with P3.
- **False-positive controls.** The shared `IGNORE_PATTERNS` suppress any NER span that overlaps a reference ID, policy date, USD amount or ratio.

## Person versus organisation

- A legal suffix (Ltd, Inc, LLC, GmbH, Corp, PLC) or a person title (Mr, Dr, Ms) is a strong cue. A strong cue that contradicts the model's label relabels the span.
- Context words (vendor, client, at / employee, analyst, CEO) are weak cues. A conflicting weak cue keeps the label but cuts confidence to 0.6x.
- When backends disagree on PERSON versus ORG, confidence is also cut to 0.6x.
- P4 does not guess. Ambiguous spans survive only at lower confidence.

## Fusion

- A structured rule finding (EMAIL, EMP_ID, …) beats any overlapping NER span.
- For PERSON, ORG and ADDRESS, NER wins over an overlapping rule span, and the rule's source is kept as agreement.
- Same-type overlaps and exact duplicates merge into one finding with the union of sources. The best confidence is kept.
- Rule findings get a fixed high confidence (0.95). Each extra distinct source adds 0.05, capped at 1.0.
- Findings below the threshold (default 0.5) are excluded from the output. They appear only in debug output.
- The result is independent of input order. A test shuffles the inputs and checks the output is identical.

## Entity resolution

Links are made on the following evidence. Shared surname alone never merges.

1. Full names merge when the surname matches, the first name matches (or one is the other's initial), and any middle initials agree. "Michael T. Achebe" and "Michael Achebe" merge. "Michael Achebe" and "Mary Achebe" do not.
2. An initial-only mention ("M. Achebe") merges only if exactly one existing person fits. If two fit, it stays separate.
3. An email whose local part matches a name merges with that person, under the same uniqueness condition.
4. An EMP ID or email in the same block (or table row) as exactly one person links to that person. An ID tied to two different people is not merged, and a conflict is reported.

Identity IDs are `PERSON_1`, `PERSON_2`, … ordered by canonical name, then first mention. They depend only on the input set.

## Metrics

Measured on a hand-labelled synthetic set: 6 files (DOCX prose, DOCX table, PPTX, image-only scanned PDF, a structured-identifier annex, and a decoy memo), 57 labels, 19 decoys (21 occurrences). Run with `.venv/bin/python eval/run_eval.py`. Full tables: `eval/results/eval_report.md`.

| Mode | Precision | Recall | F1 |
|---|---|---|---|
| NER only (spaCy; Presidio structured types and internal extractor on) | 86.8% | 80.7% | 83.6% |
| NER + mock P3 (regex rules with owner `p3`) | 88.9% | 98.2% | 93.3% |
| NER + real P3 | not run: no P3 detector is registered yet | | |

Per-type, NER only, then NER + mock P3 (P / R):

| Type | NER only | NER + mock P3 |
|---|---|---|
| PERSON | 86.7 / 92.9 | same |
| ORG | 58.3 / 100.0 | same |
| ADDRESS | 100.0 / 100.0 | same |
| EMAIL | 100.0 / 100.0 | 100.0 / 100.0 |
| EMP_ID | 100.0 / 100.0 | 100.0 / 100.0 |
| SSN, PAN, PESEL, TIN, DOB, card and account last-4, DIR, MER-IN, MER-PH | 0 / 0 | 100.0 / 100.0 |

- **Address (ADDRESS):** exact recall 100% and overlap recall 100% at every threshold tried (0.1, 0.3, 0.5). Before the pattern, exact recall was 0%. **Caveat:** the pattern was written with these sample addresses in view, so this figure overstates how well it generalises. The decoys in the memo are the only out-of-sample check, and they contain no new address shapes.
- **ORG precision:** 41.2% before the address pattern, 58.3% after. Fixed: street names that spaCy tagged as ORG (for example "Broad Street", "Admiralty Way"), which now lose to the pattern address. Remaining ORG false positives: "Audit" (twice, from "Head of Audit"), "the Risk Committee", "SSN" (label text tagged as ORG), and "Grace Achebe" in a table. spaCy gives every ORG-like span the same 0.85, so context has to do the separating.
- **Decoys:** one false positive out of 21 decoy occurrences, in the category "committee title": "the Risk Committee" tagged as ORG. Other categories held: legal-suffix org names containing a surname, title roles, sentence-start words, months, GRP references, USD amounts, RSK references, policy dates and "the Lagos office".
- **Identity (corpus, pairwise):** precision 100%, recall 94.7%. The missed pair comes from the table mention "Grace Achebe", which NER tags as ORG.
- **Mock P3 vs NER only:** the difference is the structured types, which NER never emits. Labelled PERSON and ADDRESS fields and the duplicate email do not change the scores here, because NER already finds those spans or the owner rule wins on the same span.

Caveats: 57 labels and 19 decoys is a small sample. The labels were written by the same person who wrote the pipeline. One missed label moves recall by about 1.8 points. Treat these as a regression baseline, not as production accuracy.

## Limitations

- **spaCy's scores are flat.** On the synthetic document every spaCy span came back at 0.900, so the confidence threshold separates them only through the weights and cues. Calibration needs ground truth.
- **Location is discounted to ADDRESS.** A city or country is far more often a location than a postal address, so its score is multiplied by 0.5.
- **Block IDs are random per run.** `TextBlock.block_id` is a uuid4 generated by P1. Everything else in P4 output is deterministic, but `Finding.block_id` changes between runs. Making it deterministic needs a change in P1, which was out of scope.
- **Cross-file linking needs one call.** `run_p4` links people across files only when all blocks are passed together. The per-document pipeline hook gives per-document identities.
- **cv2 is missing from `requirements.txt`.** P2 imports OpenCV, so `tests/test_ocr_pipeline.py` fails to import in a clean environment. This predates P4.

## Open decisions

1. Make `TextBlock.block_id` deterministic (for example `uuid5(source_file, reading_order)`). This needs a P1 change and approval.
2. Confirm the §16.5 and §16.8 heading format in the case document, so the priority boost matches real headings.
3. Provide a labelled sample set (ground truth) so P4 precision and recall can be measured per type and per source (body, table, slide, image_ocr).
4. Decide whether to keep GLiNER (large dependency) or rely on Presidio + spaCy only. Address recall is the case for it, but it is untested here.
5. Get a real labelled set (ground truth from real case documents) so these numbers mean something beyond this sample.
