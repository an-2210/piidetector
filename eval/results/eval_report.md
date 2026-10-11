# P4 evaluation report

Ground truth: 54 labels, 10 decoys, 5 files.
Matching: file + location + pii_type + normalised text; when a label has a span, IoU >= 0.5. Never uses block_id.

## NER only (standalone; Presidio structured recognisers and internal extractor on)

Backends: spacy. Overall: P 87.8%, R 79.6%, F1 83.5% (TP 43, FP 6, FN 11).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 12 | 2 | 1 | 85.7% | 92.3% | 88.9% |
| ORG | 6 | 4 | 0 | 60.0% | 100.0% | 75.0% |
| ADDRESS | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMAIL | 10 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMP_ID | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| DIR_ID | 0 | 0 | 1 | n/a | 0.0% | n/a |
| MER_IN_ID | 0 | 0 | 1 | n/a | 0.0% | n/a |
| MER_PH_ID | 0 | 0 | 1 | n/a | 0.0% | n/a |
| SSN | 0 | 0 | 1 | n/a | 0.0% | n/a |
| PAN | 0 | 0 | 1 | n/a | 0.0% | n/a |
| PESEL | 0 | 0 | 1 | n/a | 0.0% | n/a |
| TIN | 0 | 0 | 1 | n/a | 0.0% | n/a |
| CARD_LAST4 | 0 | 0 | 1 | n/a | 0.0% | n/a |
| ACCOUNT_LAST4 | 0 | 0 | 1 | n/a | 0.0% | n/a |
| DOB | 0 | 0 | 1 | n/a | 0.0% | n/a |

### By source type

| Source | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| body | 19 | 4 | 10 | 82.6% | 65.5% | 73.1% |
| table | 13 | 1 | 1 | 92.9% | 92.9% | 92.9% |
| slide | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| image_ocr | 5 | 1 | 0 | 83.3% | 100.0% | 90.9% |

Decoy false positives: 0.

Identity (pairwise, PERSON, corpus run): precision 100.0% (25/25 predicted pairs correct), recall 92.6% (25/27 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); structured_conflicts.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- roster_table.docx p- [table] PERSON: 'Grace Achebe'
- structured_conflicts.docx p- [body] TIN: '12-3456789'
- structured_conflicts.docx p- [body] SSN: '123-45-6789'
- structured_conflicts.docx p- [body] DOB: '14/03/1988'
- structured_conflicts.docx p- [body] PAN: '4111 1111 1111 1111'
- structured_conflicts.docx p- [body] CARD_LAST4: '4421'
- structured_conflicts.docx p- [body] PESEL: '80010112345'
- structured_conflicts.docx p- [body] ACCOUNT_LAST4: '9087'
- structured_conflicts.docx p- [body] DIR_ID: 'DIR-88421'
- structured_conflicts.docx p- [body] MER_IN_ID: 'MER-IN-449120'
- structured_conflicts.docx p- [body] MER_PH_ID: 'MER-PH-220011'

</details>

<details><summary>False positives</summary>

- prose_case.docx [body] ORG: 'Audit' (conf 0.9)
- roster_table.docx [table] ORG: 'Grace Achebe' (conf 0.68)
- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)
- structured_conflicts.docx [body] ORG: 'Audit' (conf 0.85)
- structured_conflicts.docx [body] PERSON: 'Email' (conf 0.85)
- structured_conflicts.docx [body] ORG: 'SSN' (conf 0.85)

</details>

## NER + mock P3 (regex EMAIL/EMP_ID as rule findings; defer on)

Backends: spacy. Overall: P 89.8%, R 98.1%, F1 93.8% (TP 53, FP 6, FN 1).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 12 | 2 | 1 | 85.7% | 92.3% | 88.9% |
| ORG | 6 | 4 | 0 | 60.0% | 100.0% | 75.0% |
| ADDRESS | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMAIL | 10 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMP_ID | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| DIR_ID | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| MER_IN_ID | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| MER_PH_ID | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| SSN | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| PAN | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| PESEL | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| TIN | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| CARD_LAST4 | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| ACCOUNT_LAST4 | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| DOB | 1 | 0 | 0 | 100.0% | 100.0% | 100.0% |

### By source type

| Source | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| body | 29 | 4 | 0 | 87.9% | 100.0% | 93.5% |
| table | 13 | 1 | 1 | 92.9% | 92.9% | 92.9% |
| slide | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| image_ocr | 5 | 1 | 0 | 83.3% | 100.0% | 90.9% |

Decoy false positives: 0.

Identity (pairwise, PERSON, corpus run): precision 100.0% (25/25 predicted pairs correct), recall 92.6% (25/27 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); structured_conflicts.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- roster_table.docx p- [table] PERSON: 'Grace Achebe'

</details>

<details><summary>False positives</summary>

- prose_case.docx [body] ORG: 'Audit' (conf 0.9)
- roster_table.docx [table] ORG: 'Grace Achebe' (conf 0.68)
- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)
- structured_conflicts.docx [body] ORG: 'Audit' (conf 0.85)
- structured_conflicts.docx [body] PERSON: 'Email' (conf 0.85)
- structured_conflicts.docx [body] ORG: 'SSN' (conf 0.85)

</details>

## ADDRESS diagnostics (spaCy only)

How ADDRESS is found: a deterministic street pattern (house number, capitalised name, street suffix, optional locality and city; see src/pii/address.py), with spaCy LOCATION spans used only to extend a match. spaCy LOCATION is never emitted as ADDRESS on its own. The rows below sweep the confidence threshold over the same candidates.

| Threshold | Exact recall (scoring rule) | Overlap recall (any part found) | Matched | Overlapped | Predicted | Truth | Exact precision |
|---|---|---|---|---|---|---|---|
| 0.5 | 100.0% | 100.0% | 8 | 8 | 8 | 8 | 100.0% |
| 0.3 | 100.0% | 100.0% | 8 | 8 | 8 | 8 | 100.0% |
| 0.1 | 100.0% | 100.0% | 8 | 8 | 8 | 8 | 100.0% |

Misses at the default threshold (0.5), out of 8 ADDRESS labels (empty means none):


Raw spaCy ADDRESS (LOCATION) spans found anywhere:

- none

