# P4 evaluation report

Ground truth: 39 labels, 9 decoys, 4 files.
Matching: file + location + pii_type + normalised text; when a label has a span, IoU >= 0.5. Never uses block_id.

## NER only (standalone; Presidio structured recognisers and internal extractor on)

Backends: spacy. Overall: P 81.6%, R 79.5%, F1 80.5% (TP 31, FP 7, FN 8).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 10 | 1 | 1 | 90.9% | 90.9% | 90.9% |
| ORG | 6 | 6 | 0 | 50.0% | 100.0% | 66.7% |
| ADDRESS | 0 | 0 | 7 | n/a | 0.0% | n/a |
| EMAIL | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMP_ID | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |

### By source type

| Source | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| body | 12 | 2 | 2 | 85.7% | 85.7% | 85.7% |
| table | 10 | 3 | 4 | 76.9% | 71.4% | 74.1% |
| slide | 5 | 1 | 1 | 83.3% | 83.3% | 83.3% |
| image_ocr | 4 | 1 | 1 | 80.0% | 80.0% | 80.0% |

Decoy false positives: 0.

Identity (pairwise, PERSON, corpus run): precision 100.0% (18/18 predicted pairs correct), recall 94.7% (18/19 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- briefing.pptx p2 [slide] ADDRESS: '9 Broad Street, Lagos Island'
- prose_case.docx p- [body] ADDRESS: '14 Harbour View Road, Lagos'
- prose_case.docx p- [body] ADDRESS: 'Marina Street, Ibadan'
- roster_table.docx p- [table] ADDRESS: '14 Harbour View Road, Lagos'
- roster_table.docx p- [table] ADDRESS: '7 Admiralty Way, Lekki'
- roster_table.docx p- [table] ADDRESS: '9 Broad Street, Lagos Island'
- roster_table.docx p- [table] PERSON: 'Grace Achebe'
- scanned_intake.pdf p1 [image_ocr] ADDRESS: '14 Harbour View Road, Lagos'

</details>

<details><summary>False positives</summary>

- briefing.pptx [slide] ORG: 'Broad Street' (conf 0.765)
- prose_case.docx [body] ORG: 'Ibadan' (conf 0.9)
- prose_case.docx [body] ORG: 'Audit' (conf 0.9)
- roster_table.docx [table] ORG: 'Grace Achebe' (conf 0.68)
- roster_table.docx [table] ORG: 'Admiralty Way' (conf 0.68)
- roster_table.docx [table] ORG: 'Broad Street' (conf 0.68)
- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)

</details>

## NER + mock P3 (regex EMAIL/EMP_ID as rule findings; defer on)

Backends: spacy. Overall: P 81.6%, R 79.5%, F1 80.5% (TP 31, FP 7, FN 8).

### By PII type

| Type | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| PERSON | 10 | 1 | 1 | 90.9% | 90.9% | 90.9% |
| ORG | 6 | 6 | 0 | 50.0% | 100.0% | 66.7% |
| ADDRESS | 0 | 0 | 7 | n/a | 0.0% | n/a |
| EMAIL | 8 | 0 | 0 | 100.0% | 100.0% | 100.0% |
| EMP_ID | 7 | 0 | 0 | 100.0% | 100.0% | 100.0% |

### By source type

| Source | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| body | 12 | 2 | 2 | 85.7% | 85.7% | 85.7% |
| table | 10 | 3 | 4 | 76.9% | 71.4% | 74.1% |
| slide | 5 | 1 | 1 | 83.3% | 83.3% | 83.3% |
| image_ocr | 4 | 1 | 1 | 80.0% | 80.0% | 80.0% |

Decoy false positives: 0.

Identity (pairwise, PERSON, corpus run): precision 100.0% (18/18 predicted pairs correct), recall 94.7% (18/19 truth pairs linked).

Warnings: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); briefing.pptx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); prose_case.docx: P4 identity conflict: EMAIL priya.raman@globex-ltd.com co-occurs with 2 different people; left unlinked; prose_case.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); roster_table.docx: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner); scanned_intake.pdf: P4 identity conflict: EMAIL michael.achebe@northwind-logistics.com co-occurs with 2 different people; left unlinked; scanned_intake.pdf: P4 warning: NER backend 'gliner' skipped: gliner is not installed (pip install gliner)

<details><summary>Missed labels</summary>

- briefing.pptx p2 [slide] ADDRESS: '9 Broad Street, Lagos Island'
- prose_case.docx p- [body] ADDRESS: '14 Harbour View Road, Lagos'
- prose_case.docx p- [body] ADDRESS: 'Marina Street, Ibadan'
- roster_table.docx p- [table] ADDRESS: '14 Harbour View Road, Lagos'
- roster_table.docx p- [table] ADDRESS: '7 Admiralty Way, Lekki'
- roster_table.docx p- [table] ADDRESS: '9 Broad Street, Lagos Island'
- roster_table.docx p- [table] PERSON: 'Grace Achebe'
- scanned_intake.pdf p1 [image_ocr] ADDRESS: '14 Harbour View Road, Lagos'

</details>

<details><summary>False positives</summary>

- briefing.pptx [slide] ORG: 'Broad Street' (conf 0.765)
- prose_case.docx [body] ORG: 'Ibadan' (conf 0.9)
- prose_case.docx [body] ORG: 'Audit' (conf 0.9)
- roster_table.docx [table] ORG: 'Grace Achebe' (conf 0.68)
- roster_table.docx [table] ORG: 'Admiralty Way' (conf 0.68)
- roster_table.docx [table] ORG: 'Broad Street' (conf 0.68)
- scanned_intake.pdf [image_ocr] PERSON: 'Email' (conf 0.68)

</details>

## NER + real P3 (registered detector)

**Skipped:** no P3 rule detector registered or importable (src.pii.rules.get_detector)

## ADDRESS diagnostics (spaCy only)

How spaCy handles ADDRESS: Presidio's spaCy recogniser tags LOCATION spans. The backend maps LOCATION to ADDRESS and multiplies the score by 0.5, because cities and countries are not postal addresses. A typical LOCATION score (0.85) therefore becomes 0.425, which is below the default threshold of 0.5, so it is dropped. In the sample, spaCy tags only the city or a street fragment, never the whole address, so exact recall stays at zero even when the threshold is lowered.

| Threshold | Exact recall (scoring rule) | Overlap recall (any part found) | Matched | Overlapped | Predicted | Truth | Exact precision |
|---|---|---|---|---|---|---|---|
| 0.5 | 0.0% | 0.0% | 0 | 0 | 0 | 7 | n/a |
| 0.3 | 0.0% | 85.7% | 0 | 6 | 6 | 7 | 0.0% |
| 0.1 | 0.0% | 85.7% | 0 | 6 | 6 | 7 | 0.0% |

Misses at the default threshold (0.5), out of 7 ADDRESS labels:

- briefing.pptx [slide] '9 Broad Street, Lagos Island': spaCy: 'Broad Street' label ORG raw 0.85; 'Lagos Island' label ADDRESS raw 0.425. Fused candidates: 'Broad Street' ORG conf 0.765; 'Lagos Island' ADDRESS conf 0.3825.
- prose_case.docx [body] '14 Harbour View Road, Lagos': spaCy: 'Lagos' label ADDRESS raw 0.425. Fused candidates: 'Lagos' ADDRESS conf 0.475.
- prose_case.docx [body] 'Marina Street, Ibadan': spaCy: 'Marina Street' label ADDRESS raw 0.425; 'Ibadan' label ORG raw 0.85. Fused candidates: 'Marina Street' ADDRESS conf 0.475; 'Ibadan' ORG conf 0.9.
- roster_table.docx [table] '14 Harbour View Road, Lagos': spaCy: 'Lagos' label ADDRESS raw 0.425. Fused candidates: 'Lagos' ADDRESS conf 0.34.
- roster_table.docx [table] '7 Admiralty Way, Lekki': spaCy: 'Admiralty Way' label ORG raw 0.85. Fused candidates: 'Admiralty Way' ORG conf 0.68.
- roster_table.docx [table] '9 Broad Street, Lagos Island': spaCy: 'Broad Street' label ORG raw 0.85; 'Lagos Island' label ADDRESS raw 0.425. Fused candidates: 'Broad Street' ORG conf 0.68; 'Lagos Island' ADDRESS conf 0.34.
- scanned_intake.pdf [image_ocr] '14 Harbour View Road, Lagos': spaCy: 'Lagos' label ADDRESS raw 0.425. Fused candidates: 'Lagos' ADDRESS conf 0.34.

Raw spaCy ADDRESS (LOCATION) spans found anywhere:

- briefing.pptx: 'Lagos Island' raw 0.425
- prose_case.docx: 'Lagos' raw 0.425
- prose_case.docx: 'Marina Street' raw 0.425
- roster_table.docx: 'Lagos' raw 0.425
- roster_table.docx: 'Lagos Island' raw 0.425
- scanned_intake.pdf: 'Lagos' raw 0.425

