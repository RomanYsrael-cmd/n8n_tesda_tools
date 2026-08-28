---
schema: tesda-trmd
schema_version: "1.0"
document_id: tesda:tr:bookkeeping-nc-iii:2007
title: Bookkeeping NC III
sector: Health, Social, and Other Community Development Services Sector
credential:
  system: NC
  level: 3
  label: NC III
promulgated: "2007-11"
content_status: complete
source:
  authority: Technical Education and Skills Development Authority (TESDA)
  original_document: Bookkeeping NC III Training Regulations
  official_url: "https://tesda.gov.ph/Downloadables/TR%20BOOKKEEPING%20NC%20III.pdf"
  printed_pages: 1-69
---

# Bookkeeping NC III — Indexed Training Regulation

This directory is the complete semantic representation of the TESDA **Bookkeeping NC III** Training Regulations promulgated in **November 2007**. It is designed for human reading and deterministic retrieval by scripts, n8n workflows, search systems, and LLMs. The original TESDA PDF remains the authoritative regulatory source.

## 1. Qualification

The qualification covers the competencies required to journalize transactions, post transactions, prepare a trial balance, prepare financial reports, and review an internal control system.

### Occupational outcomes

- Bookkeeper
- Accounting Clerk

### Competency requirements

#### Basic competencies

| Unit code | Unit of competency |
|---|---|
| `500311109` | Lead workplace communication |
| `500311110` | Lead small team |
| `500311111` | Develop and practice negotiation skills |
| `500311112` | Solve problems related to work activities |
| `500311113` | Use mathematical concepts and techniques |
| `500311114` | Use relevant technologies |

#### Common competencies

| Unit code | Unit of competency |
|---|---|
| `HCS315202` | Apply quality standards |
| `HCS311201` | Perform computer operations |
| `HCS913201` | Maintain an effective relationship with clients and customers |
| `HCS913202` | Manage own performance |

#### Core competencies

| Unit code | Unit of competency |
|---|---|
| `HCS412301` | Journalize transactions |
| `HCS412302` | Post transactions |
| `HCS412303` | Prepare trial balance |
| `HCS412304` | Prepare financial reports |
| `HCS412305` | Review internal control system |

## 2. Competency Standards

[`competencies.yaml`](./competencies.yaml) is the canonical semantic representation of all **15 competency units**: 6 Basic, 4 Common, and 5 Core. Each unit contains its descriptor, elements, performance criteria, range of variables, evidence guide, and printed-page provenance.

The core bookkeeping workflow is:

1. `HCS412301` — Journalize Transactions
2. `HCS412302` — Post Transactions
3. `HCS412303` — Prepare Trial Balance
4. `HCS412304` — Prepare Financial Reports
5. `HCS412305` — Review Internal Control System

## 3. Training Standards

The original 2007 source calls Section 3 **TRAINING STANDARDS**. [`training-standards.yaml`](./training-standards.yaml) represents all seven subsections.

### 3.1 Curriculum Design

- Course title: **Bookkeeping**
- Level: **NC III**
- Basic competencies: **20 hours**
- Common competencies: **24 hours**
- Core competencies: **248 hours**
- Total nominal duration: **292 hours**

The structured curriculum records each unit's learning outcomes, methodology and assessment approach.

### 3.2 Training Delivery

The indexed data preserves the source's competency-based TVET principles and its listed delivery modalities: dualized training, modular/self-paced learning, peer teaching/mentoring, supervised industry training/OJT, distance learning, and project-based instruction.

### 3.3 Trainee Entry Requirements

The indexed data preserves the source requirements for oral/written communication, physical/emotional/psychological/mental fitness, and basic mathematical computation.

### 3.4 Tools, Equipment and Materials

The source uses a minimum class-size basis of 25 trainees. The complete table is represented in `training-standards.yaml`, including legacy items such as diskettes/CD. Where the TESDA source itself leaves a quantity cell blank, the structured representation keeps the source blank instead of inventing a value.

### 3.5 Training Facilities

The source specifies **104 sq. m.** total for 25 trainees: 25 sq. m. trainee working space, 40 sq. m. lecture/demo room, 15 sq. m. learning resource center, and 24 sq. m. facilities/equipment/circulation area.

### 3.6 Trainer Qualifications

The source requires Bookkeeping NC III or CPA qualification, BS Accounting or equivalent, Training Methodology III or equivalent, effective oral/written communication, at least three years of bookkeeping industry experience, and good moral character.

### 3.7 Institutional Assessment

Institutional assessment determines achievement per unit of competency, with a certificate of achievement issued for each achieved unit.

## 4. National Assessment and Certification Arrangements

[`assessment-certification.yaml`](./assessment-certification.yaml) represents all nine provisions, 4.1 through 4.9, including project-type assessment, eligibility, reassessment rules, assessor restrictions, accredited assessment-center requirements, and the TESDA procedural references named by the source.

## 5. Competency Map

[`competency-map.yaml`](./competency-map.yaml) represents the complete printed competency map as Basic, Common and Core unit relationships and codes.

## 6. Definition of Terms

[`glossary.yaml`](./glossary.yaml) contains the complete normalized glossary from printed pages 63–67.

## 7. Acknowledgements

[`acknowledgements.yaml`](./acknowledgements.yaml) represents the technical/industry experts, national-validation participants, and institutional acknowledgements from printed pages 68–69.

## Retrieval Contract

Use [`semantic-index.jsonl`](./semantic-index.jsonl) as the lightweight locator, then retrieve the matching canonical record rather than passing the entire Training Regulation to an LLM.

```text
Need: Prepare Financial Reports
Lookup: unit_code == HCS412304
Index: semantic-index.jsonl
Canonical: competencies.yaml -> HCS412304
Training context: training-standards.yaml -> HCS412304
```

This package contains no placeholder or pending-transcription sections. Source-era wording and requirements are retained semantically instead of silently modernized.
