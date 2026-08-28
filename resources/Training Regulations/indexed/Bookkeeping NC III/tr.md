---
schema: tesda-trmd
schema_version: "1.1"
document_id: tesda:tr:bookkeeping-nc-iii:2007
title: Bookkeeping NC III
sector: Health, Social, and Other Community Development Services Sector
credential:
  system: NC
  level: 3
  label: NC III
promulgated: "2007-11"
coverage_status: complete
representation_type: semantic_normalized
verbatim_transcription: false
source:
  authority: Technical Education and Skills Development Authority (TESDA)
  original_document: Bookkeeping NC III Training Regulations
  official_url: "https://tesda.gov.ph/Downloadables/TR%20BOOKKEEPING%20NC%20III.pdf"
  printed_pages: 1-69
  pdf_pages: 71
---

# Bookkeeping NC III — Indexed Training Regulation

This directory provides complete **semantic coverage** of the TESDA **Bookkeeping NC III** Training Regulations promulgated in **November 2007**. It is designed for human reading and deterministic retrieval by scripts, n8n workflows, search systems, and LLMs.

It is not a verbatim regulatory transcription. The original TESDA PDF remains the authoritative source. Normalized records are separated from fidelity-sensitive source details in [`source-fidelity.yaml`](./source-fidelity.yaml).

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

[`competencies.yaml`](./competencies.yaml) is the normalized semantic representation of all **15 competency units**: 6 Basic, 4 Common, and 5 Core. Each unit represents its descriptor, elements, performance criteria, range of variables, and evidence guide.

The canonical competency file is optimized for retrieval rather than literal table transcription. Where a longer Evidence Guide contains assessment instructions that materially affect scenario design, evidence collection, simulation, or context, those fidelity-sensitive additions can be attached through [`source-fidelity.yaml`](./source-fidelity.yaml).

The core bookkeeping workflow is:

1. `HCS412301` — Journalize Transactions
2. `HCS412302` — Post Transactions
3. `HCS412303` — Prepare Trial Balance
4. `HCS412304` — Prepare Financial Reports
5. `HCS412305` — Review Internal Control System

Historical regulatory terminology remains intact at the semantic level. For example, the 2007 TR uses **Income Statement** and **Balance Sheet**; instructional material may map these to newer terminology, but the regulatory index must not silently rewrite them.

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

The indexed data preserves the source's competency-based TVET principles and its listed delivery modalities, including dualized training, modular/self-paced learning, peer teaching/mentoring, supervised industry training/OJT, distance learning, and project-based instruction.

### 3.3 Trainee Entry Requirements

The indexed data preserves the source requirements for oral/written communication, physical/emotional/psychological/mental fitness, and basic mathematical computation.

### 3.4 Tools, Equipment and Materials

The source uses a minimum class-size basis of 25 trainees. The structured representation includes legacy items such as diskettes/CD. Where the TESDA source leaves a quantity cell blank, the semantic representation keeps it blank rather than inventing a value.

### 3.5 Training Facilities

The source specifies **104 sq. m.** total for 25 trainees: 25 sq. m. trainee working space, 40 sq. m. lecture/demo room, 15 sq. m. learning resource center, and 24 sq. m. facilities/equipment/circulation area.

### 3.6 Trainer Qualifications

The source requires Bookkeeping NC III or CPA qualification, BS Accounting or equivalent, Training Methodology III or equivalent, effective oral/written communication, at least three years of bookkeeping industry experience, and good moral character.

### 3.7 Institutional Assessment

Institutional assessment determines achievement per unit of competency, with a certificate of achievement issued for each achieved unit.

## 4. National Assessment and Certification Arrangements

[`assessment-certification.yaml`](./assessment-certification.yaml) represents all nine provisions, 4.1 through 4.9, including project-type assessment, eligibility, reassessment rules, assessor restrictions, accredited assessment-center requirements, and the TESDA procedural references named by the source.

Provision **4.7** contains an apparent source wording error. The normalized interpretation is kept usable while the source anomaly is explicitly preserved in [`source-fidelity.yaml`](./source-fidelity.yaml).

## 5. Competency Map

[`competency-map.yaml`](./competency-map.yaml) represents the printed competency map as Basic, Common and Core unit relationships and codes. This is a semantic relationship representation, not a reconstruction of the source's visual layout.

## 6. Definition of Terms

[`glossary.yaml`](./glossary.yaml) contains a normalized glossary covering printed pages 63–67. Source wording that appears erroneous is not silently erased: the normalized term links to a source-fidelity record. The **Sales invoice** entry is one documented example.

## 7. Acknowledgements

[`acknowledgements.yaml`](./acknowledgements.yaml) represents the technical/industry experts, national-validation participants, and institutional acknowledgements from printed pages 68–69. It is an entity-focused semantic representation rather than a verbatim reproduction of every presentation detail or postal address.

## Source-Fidelity Layer

[`source-fidelity.yaml`](./source-fidelity.yaml) is the bridge between source-sensitive regulatory use and lightweight semantic retrieval. It currently records:

- expanded assessment instructions for `500311112` that were compressed in the canonical Evidence Guide;
- the Section 4.7 source anomaly and normalized interpretation;
- the Sales invoice glossary anomaly and normalized interpretation; and
- representation notes for the competency map and acknowledgements.

If a task is assessment-sensitive, regulatory, or asks what TESDA literally/approximately says, retrieve the matching fidelity record in addition to the canonical semantic record.

## Retrieval Contract

Use [`semantic-index.jsonl`](./semantic-index.jsonl) as the lightweight locator. It uses explicit selectors rather than pseudo-anchors.

```text
Need: Prepare Financial Reports
Lookup: unit_code == HCS412304
Index: semantic-index.jsonl
Canonical file: competencies.yaml
Selector: field=unit_code, value=HCS412304
Training context: training-standards.yaml -> curriculum_design/core unit HCS412304
```

For `field` + `value`, the resolver must return the unique mapping whose direct field matches the value. For `kind: yaml_path`, it follows the exact dot-separated mapping path. Multiple matches are an error; the resolver must never choose one silently.

If an index record exposes `fidelity_ref`, also retrieve the matching `source-fidelity.yaml` record when source fidelity matters.

This package contains no placeholder or pending-transcription sections. That statement means **semantic coverage is complete**; it does not mean the package is a verbatim regulatory-grade transcription.
