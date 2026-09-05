# Housekeeping NC III — Indexed TESDA Training Regulation

This folder is the human-, machine-, and AI-readable **semantic representation** of the TESDA **Housekeeping NC III** Training Regulation, qualification code **TRSHSK319**, Revision 01, promulgated **October 15, 2019**.

This package has complete semantic coverage but is not a verbatim regulatory transcription. The official TESDA PDF remains authoritative.

## Representation Layers

Keep the layers separate:

```text
Official TESDA PDF
        ↓
source-fidelity layer
        ↓
normalized semantic representation
        ↓
instructional interpretation / Module Builder
```

**TESDA source ≠ normalized semantic representation ≠ instructional interpretation.**

The source-fidelity layer records source anomalies, visual/table-extraction recoveries, and assessment-sensitive details that must not be silently normalized away.

## Source and lifecycle

- Qualification: **Housekeeping NC III**
- Qualification code: **TRSHSK319**
- Sector: **Tourism Sector (Hotel and Restaurant)**
- Revision: **01**
- Promulgated: **10/15/2019**
- TESDA Board Resolution: **2019-56**
- Current status verified against TESDA's Training Regulations portal on **2026-09-02**.
- Repository source: `resources/Training Regulations/Housekeeping NC III.pdf`
- Official TESDA PDF: `https://www.tesda.gov.ph/Downloadables/TRs/TR_HOUSEKEEPING_NC%20III.pdf`

## Coverage

The package represents all **20 qualification units**: 9 Basic, 7 Common, and 4 Core. It includes every unit descriptor, element, Performance Criterion, Required Knowledge item, Required Skills item, Range of Variables, and Evidence Guide; the full Section 3 curriculum and training arrangements; all Section 4 provisions; the competency-map relationships; all 43 glossary entries; revision history; and acknowledgements.

Nominal duration is **40 Basic + 96 Common + 64 Core = 200 hours**, plus **64 hours Supervised Industry Learning**, for **264 hours total**.

## Files

| File | Purpose |
|---|---|
| `tr.md` | Human-readable qualification entry point |
| `competencies.yaml` | Complete Basic/Common/Core competency standards |
| `training-standards.yaml` | Section 3 curriculum and training arrangements |
| `assessment-certification.yaml` | Section 4 national assessment/certification provisions |
| `competency-map.yaml` | Semantic representation of the printed competency map |
| `glossary.yaml` | All 43 glossary terms and definitions |
| `acknowledgements.yaml` | Experts, validation participants, institutions and facilitators |
| `source-fidelity.yaml` | Source anomalies, fidelity-sensitive details and visual recoveries |
| `semantic-index.jsonl` | Deterministic locator for n8n, scripts and RAG |
| `manifest.json` | Coverage, lifecycle, fidelity and retrieval declaration |

## Retrieval Contract — `semantic-index-v1`

Do not treat locator strings as pseudo-anchors. `semantic-index.jsonl` uses explicit selectors.

A selector such as:

```json
{"field":"unit_code","value":"TRS515301"}
```

means: recursively search mappings/sequence items in the canonical YAML file and return the **unique mapping whose direct field** `unit_code` equals `TRS515301`.

A selector such as:

```json
{"kind":"yaml_path","value":"curriculum_design"}
```

means: follow that exact dot-separated mapping path.

Resolver rules:

1. `field` + `value` performs a recursive search for direct-field matches.
2. A valid field selector must resolve to exactly one mapping.
3. `kind: yaml_path` follows an exact mapping path; it must exist.
4. A missing selector means the whole canonical file is the target.
5. Never silently select one result if multiple matches exist.
6. If the index record has `fidelity_ref`, retrieve the matching `record_id` from `source-fidelity.yaml` for regulatory, source-sensitive, or assessment-sensitive tasks.
7. If semantic content and the official source appear to conflict, the official TESDA PDF controls.

## Recommended Module Builder / RAG flow

```text
module need
   ↓
semantic-index.jsonl
   ↓
small canonical YAML record
   ↓
source-fidelity record when applicable
   ↓
LLM instructional interpretation
```

For ordinary module generation, do not send the entire 143-page PDF. For exact regulatory verification, unresolved ambiguity, or source-sensitive assessment questions, consult the official PDF.

There are **no TODOs, placeholders, or pending-transcription sections** in this package. “Complete” refers to semantic coverage, not verbatim reproduction of the regulation.
