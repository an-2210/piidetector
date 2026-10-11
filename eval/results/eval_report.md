# P4 evaluation report

Ground truth: 39 labels, 9 decoys, 4 files.
Matching: file + location + pii_type + normalised text; when a label has a span, IoU >= 0.5. Never uses block_id.

## NER only (standalone; Presidio structured recognisers and internal extractor on)

Backends: spacy. Overall: P 92.7%, R 97.4%, F1 95.0% (TP 38, FP 3, FN 1).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 10 | 1 | 1 | 90.9% | 90.9% | 90.9% |
| ORG | 6 | 2 | 0 | 75.0% | 100.0% | 85.7% |
| ADDRESS | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMAIL | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMP_ID | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |

### By source type

| Source | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| body | 14 | 1 | 0 | 93.3% | 100.0% | 96.6% |
| table | 13 | 1 | 1 | 92.9% | 92.9% | 92.9% |
| slide | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| image_ocr | 5 | 1 | 0 | 83.3% | 100.0% | 90.9% |

Decoy false positives: 0.

Identity (pairwise, PERSON, corpus run): precision 100.0% (18/18 predicted pairs correct), recall 94.7% (18/19 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- roster_table.docx p- [table] PERSON: 'Grace Achebe'

</details>

<details><summary>False positives</summary>

- prose_case.docx [body] ORG: 'Audit' (conf 0.9)
- roster_table.docx [table] ORG: 'Grace Achebe' (conf 0.68)
- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)

</details>

## NER + mock P3 (regex EMAIL/EMP_ID as rule findings; defer on)

Backends: spacy. Overall: P 92.7%, R 97.4%, F1 95.0% (TP 38, FP 3, FN 1).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 10 | 1 | 1 | 90.9% | 90.9% | 90.9% |
| ORG | 6 | 2 | 0 | 75.0% | 100.0% | 85.7% |
| ADDRESS | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMAIL | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMP_ID | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |

### By source type

| Source | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| body | 14 | 1 | 0 | 93.3% | 100.0% | 96.6% |
| table | 13 | 1 | 1 | 92.9% | 92.9% | 92.9% |
| slide | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| image_ocr | 5 | 1 | 0 | 83.3% | 100.0% | 90.9% |

Decoy false positives: 0.

Identity (pairwise, PERSON, corpus run): precision 100.0% (18/18 predicted pairs correct), recall 94.7% (18/19 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- roster_table.docx p- [table] PERSON: 'Grace Achebe'

</details>

<details><summary>False positives</summary>

- prose_case.docx [body] ORG: 'Audit' (conf 0.9)
- roster_table.docx [table] ORG: 'Grace Achebe' (conf 0.68)
- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)

</details>

## ADDRESS diagnostics (spaCy only)

How spaCy handles ADDRESS: Presidio's spaCy recogniser tags LOCATION spans. The backend maps LOCATION to ADDRESS and multiplies the score by 0.5, because cities and countries are not postal addresses. A typical LOCATION score (0.85) therefore becomes 0.425, which is below the default threshold of 0.5, so it is dropped. In the sample, spaCy tags only the city or a street fragment, never the whole address, so exact recall stays at zero even when the threshold is lowered.

| Threshold | Exact recall (scoring rule) | Overlap recall (any part found) | Matched | Overlapped | Predicted | Truth | Exact precision |
|---|---|---|---|---|---|---|---|
| 0.5 | 100.0% | 100.0% | 7 | 7 | 7 | 7 | 100.0% |
| 0.3 | 100.0% | 100.0% | 7 | 7 | 7 | 7 | 100.0% |
| 0.1 | 100.0% | 100.0% | 7 | 7 | 7 | 7 | 100.0% |

Misses at the default threshold (0.5), out of 7 ADDRESS labels:


Raw spaCy ADDRESS (LOCATION) spans found anywhere:

- none

