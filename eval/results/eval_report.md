# P4 evaluation report

Ground truth: 57 labels, 25 decoys, 6 files.
Matching: file + location + pii_type + normalised text; when a label has a span, IoU >= 0.5. Never uses block_id.

## NER only (standalone; Presidio structured recognisers and internal extractor on) [ORG emitted]

Backends: spacy. Overall: P 95.9%, R 82.5%, F1 88.7% (TP 47, FP 2, FN 10).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 14 | 2 | 0 | 87.5% | 100.0% | 93.3% |
| ORG | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| ADDRESS | 9 | 0 | 0 | 100.0% | 100.0% | 100.0% |
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
| body | 22 | 1 | 10 | 95.7% | 68.8% | 80.0% |
| table | 14 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| slide | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| image_ocr | 5 | 1 | 0 | 83.3% | 100.0% | 90.9% |

Decoy false positives: 0 (of 27 decoy occurrences).

| Decoy category | Decoys | Occurrences | False positives |
|---|---|---|---|
| rsk_ref | 5 | 5 | 0 |
| usd_amount | 4 | 4 | 0 |
| policy_date | 2 | 2 | 0 |
| committee_title | 1 | 2 | 0 |
| title_role | 1 | 1 | 0 |
| org_contains_person | 1 | 1 | 0 |
| place_non_address | 1 | 1 | 0 |
| sentence_start_word | 2 | 2 | 0 |
| month_name | 1 | 2 | 0 |
| grp_ref | 1 | 1 | 0 |
| org_generic_word | 2 | 2 | 0 |
| org_role_phrase | 1 | 1 | 0 |
| org_pii_label | 2 | 2 | 0 |
| org_unit_phrase | 1 | 1 | 0 |

Identity (pairwise, PERSON, corpus run): precision 100.0% (27/27 predicted pairs correct), recall 100.0% (27/27 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); decoys_memo.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); structured_conflicts.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

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

- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)
- structured_conflicts.docx [body] PERSON: 'Email' (conf 0.85)

</details>

## NER only (standalone; Presidio structured recognisers and internal extractor on) [ORG suppressed (used for disambiguation only)]

Backends: spacy. Overall: P 95.2%, R 70.2%, F1 80.8% (TP 40, FP 2, FN 17).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 14 | 2 | 0 | 87.5% | 100.0% | 93.3% |
| ORG | 0 | 0 | 7 | n/a | 0.0% | n/a |
| ADDRESS | 9 | 0 | 0 | 100.0% | 100.0% | 100.0% |
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
| body | 18 | 1 | 14 | 94.7% | 56.2% | 70.6% |
| table | 13 | 0 | 1 | 100.0% | 92.9% | 96.3% |
| slide | 5 | 0 | 1 | 100.0% | 83.3% | 90.9% |
| image_ocr | 4 | 1 | 1 | 80.0% | 80.0% | 80.0% |

Decoy false positives: 0 (of 27 decoy occurrences).

| Decoy category | Decoys | Occurrences | False positives |
|---|---|---|---|
| rsk_ref | 5 | 5 | 0 |
| usd_amount | 4 | 4 | 0 |
| policy_date | 2 | 2 | 0 |
| committee_title | 1 | 2 | 0 |
| title_role | 1 | 1 | 0 |
| org_contains_person | 1 | 1 | 0 |
| place_non_address | 1 | 1 | 0 |
| sentence_start_word | 2 | 2 | 0 |
| month_name | 1 | 2 | 0 |
| grp_ref | 1 | 1 | 0 |
| org_generic_word | 2 | 2 | 0 |
| org_role_phrase | 1 | 1 | 0 |
| org_pii_label | 2 | 2 | 0 |
| org_unit_phrase | 1 | 1 | 0 |

Identity (pairwise, PERSON, corpus run): precision 100.0% (27/27 predicted pairs correct), recall 100.0% (27/27 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); decoys_memo.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); structured_conflicts.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- briefing.pptx p2 [slide] ORG: 'Globex Ltd'
- decoys_memo.docx p- [body] ORG: 'Achebe Holdings Ltd'
- prose_case.docx p- [body] ORG: 'Acme Corp'
- prose_case.docx p- [body] ORG: 'Globex Ltd'
- prose_case.docx p- [body] ORG: 'Northwind Logistics Ltd'
- roster_table.docx p- [table] ORG: 'Acme Corp'
- scanned_intake.pdf p1 [image_ocr] ORG: 'Acme Corp'
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

- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)
- structured_conflicts.docx [body] PERSON: 'Email' (conf 0.85)

</details>

## NER + mock P3 (regex EMAIL/EMP_ID as rule findings; defer on) [ORG emitted]

Backends: spacy. Overall: P 96.6%, R 100.0%, F1 98.3% (TP 57, FP 2, FN 0).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 14 | 2 | 0 | 87.5% | 100.0% | 93.3% |
| ORG | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| ADDRESS | 9 | 0 | 0 | 100.0% | 100.0% | 100.0% |
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
| body | 32 | 1 | 0 | 97.0% | 100.0% | 98.5% |
| table | 14 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| slide | 6 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| image_ocr | 5 | 1 | 0 | 83.3% | 100.0% | 90.9% |

Decoy false positives: 0 (of 27 decoy occurrences).

| Decoy category | Decoys | Occurrences | False positives |
|---|---|---|---|
| rsk_ref | 5 | 5 | 0 |
| usd_amount | 4 | 4 | 0 |
| policy_date | 2 | 2 | 0 |
| committee_title | 1 | 2 | 0 |
| title_role | 1 | 1 | 0 |
| org_contains_person | 1 | 1 | 0 |
| place_non_address | 1 | 1 | 0 |
| sentence_start_word | 2 | 2 | 0 |
| month_name | 1 | 2 | 0 |
| grp_ref | 1 | 1 | 0 |
| org_generic_word | 2 | 2 | 0 |
| org_role_phrase | 1 | 1 | 0 |
| org_pii_label | 2 | 2 | 0 |
| org_unit_phrase | 1 | 1 | 0 |

Identity (pairwise, PERSON, corpus run): precision 100.0% (27/27 predicted pairs correct), recall 100.0% (27/27 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); decoys_memo.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); structured_conflicts.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>False positives</summary>

- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)
- structured_conflicts.docx [body] PERSON: 'Email' (conf 0.85)

</details>

## NER + mock P3 (regex EMAIL/EMP_ID as rule findings; defer on) [ORG suppressed (used for disambiguation only)]

Backends: spacy. Overall: P 96.2%, R 87.7%, F1 91.7% (TP 50, FP 2, FN 7).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 14 | 2 | 0 | 87.5% | 100.0% | 93.3% |
| ORG | 0 | 0 | 7 | n/a | 0.0% | n/a |
| ADDRESS | 9 | 0 | 0 | 100.0% | 100.0% | 100.0% |
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
| body | 28 | 1 | 4 | 96.6% | 87.5% | 91.8% |
| table | 13 | 0 | 1 | 100.0% | 92.9% | 96.3% |
| slide | 5 | 0 | 1 | 100.0% | 83.3% | 90.9% |
| image_ocr | 4 | 1 | 1 | 80.0% | 80.0% | 80.0% |

Decoy false positives: 0 (of 27 decoy occurrences).

| Decoy category | Decoys | Occurrences | False positives |
|---|---|---|---|
| rsk_ref | 5 | 5 | 0 |
| usd_amount | 4 | 4 | 0 |
| policy_date | 2 | 2 | 0 |
| committee_title | 1 | 2 | 0 |
| title_role | 1 | 1 | 0 |
| org_contains_person | 1 | 1 | 0 |
| place_non_address | 1 | 1 | 0 |
| sentence_start_word | 2 | 2 | 0 |
| month_name | 1 | 2 | 0 |
| grp_ref | 1 | 1 | 0 |
| org_generic_word | 2 | 2 | 0 |
| org_role_phrase | 1 | 1 | 0 |
| org_pii_label | 2 | 2 | 0 |
| org_unit_phrase | 1 | 1 | 0 |

Identity (pairwise, PERSON, corpus run): precision 100.0% (27/27 predicted pairs correct), recall 100.0% (27/27 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); decoys_memo.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); structured_conflicts.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- briefing.pptx p2 [slide] ORG: 'Globex Ltd'
- decoys_memo.docx p- [body] ORG: 'Achebe Holdings Ltd'
- prose_case.docx p- [body] ORG: 'Acme Corp'
- prose_case.docx p- [body] ORG: 'Globex Ltd'
- prose_case.docx p- [body] ORG: 'Northwind Logistics Ltd'
- roster_table.docx p- [table] ORG: 'Acme Corp'
- scanned_intake.pdf p1 [image_ocr] ORG: 'Acme Corp'

</details>

<details><summary>False positives</summary>

- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)
- structured_conflicts.docx [body] PERSON: 'Email' (conf 0.85)

</details>

## NER + real P3 (registered detector) [ORG emitted]

**Skipped:** no P3 rule detector registered or importable (src.pii.rules.get_detector)

## NER + real P3 (registered detector) [ORG suppressed (used for disambiguation only)]

**Skipped:** no P3 rule detector registered or importable (src.pii.rules.get_detector)

## ADDRESS diagnostics (spaCy only)

How ADDRESS is found: a deterministic street pattern (house number, capitalised name, street suffix, optional locality and city; see src/pii/address.py), with spaCy LOCATION spans used only to extend a match. spaCy LOCATION is never emitted as ADDRESS on its own. The rows below sweep the confidence threshold over the same candidates.

| Threshold | Exact recall (scoring rule) | Overlap recall (any part found) | Matched | Overlapped | Predicted | Truth | Exact precision |
|---|---|---|---|---|---|---|---|
| 0.5 | 100.0% | 100.0% | 9 | 9 | 9 | 9 | 100.0% |
| 0.3 | 100.0% | 100.0% | 9 | 9 | 9 | 9 | 100.0% |
| 0.1 | 100.0% | 100.0% | 9 | 9 | 9 | 9 | 100.0% |

Misses at the default threshold (0.5), out of 9 ADDRESS labels (empty means none):


Raw spaCy ADDRESS (LOCATION) spans found anywhere:

- none

