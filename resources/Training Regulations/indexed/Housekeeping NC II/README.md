# Housekeeping NC II — Indexed TESDA Training Regulation

This folder is the human-, machine-, and AI-readable **semantic representation** of the TESDA **Housekeeping NC II** Training Regulations, **Amended** and promulgated in **December 2013**.

**Lifecycle verification:** current as of **2026-09-02**. TESDA's current Training Regulations portal lists **Housekeeping NC II** without a “Superseded” label. The official TESDA PDF remains authoritative.

> This package has complete semantic coverage but is not a verbatim regulatory transcription. The official TESDA PDF remains authoritative.

## Representation layers

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

The official PDF controls regulatory/source verification. `source-fidelity.yaml` records source anomalies and interpretation-sensitive details. The normalized YAML/JSONL files are designed for deterministic retrieval, n8n, Python, RAG and small/local LLMs. Downstream Module Builder output is instructional interpretation and must not silently rewrite the regulatory index.

## Source identity

- Qualification: **Housekeeping NC II**
- Sector: **Tourism Sector (Hotel and Restaurant)**
- Credential level: **NC II**
- Source revision: **Amended**
- Promulgated: **December 2013**
- Official PDF: `https://www.tesda.gov.ph/Downloadables/TR%20Housekeeping%20NC%20II.pdf`
- Repository PDF: `resources/Training Regulations/Housekeeping NC II.pdf`
- PDF pages: **70 physical pages** (67 content pages: 4 front-matter pages + printed pages 1–63, followed by 3 trailing blank pages)
- Repository blob SHA: `853866dcef6b8aa67d1bf63a8ea89dae1e1b6baf`
- SHA-256: `4c1b23cdbed2f1d170e6d6de23d283f9a606a8959b2591386be84084a40fe970`

The uploaded PDF used during indexing is byte-identical to the repository PDF (matching Git blob SHA).

## Package files

| File | Purpose |
|---|---|
| `tr.md` | Human-readable qualification and package map |
| `competencies.yaml` | All 15 Basic/Common/Core competency standards, including descriptors, elements, PCs, Range of Variables and Evidence Guides |
| `training-standards.yaml` | Complete Section 3 curriculum, delivery, entry requirements, resources, facilities, trainer qualifications and institutional assessment |
| `assessment-certification.yaml` | Complete Section 4 national assessment/certification arrangements and COC pathways |
| `competency-map.yaml` | Semantic representation of Annex A and qualification membership |
| `glossary.yaml` | All eight Definition of Terms entries |
| `acknowledgements.yaml` | Review panel, validation participants and institutional acknowledgements |
| `source-fidelity.yaml` | Source inconsistencies, probable typos and fidelity-sensitive structural interpretation |
| `semantic-index.jsonl` | Deterministic retrieval records with explicit selectors |
| `manifest.json` | Coverage, lifecycle, fidelity, source and quality declarations |

## Coverage

The package represents **4 Basic**, **5 Common**, and **6 Core** units (15 total). Section 3 gives nominal group durations of **18 Basic + 18 Common + 400 Core = 436 hours**. The arithmetic total is stored with an explicit calculation note because the PDF prints the three group durations but does not print a grand total.

No per-unit nominal-duration column exists in the curriculum table, so no per-unit duration is invented.

## Important source-fidelity findings

The official PDF contains several internal irregularities that are preserved rather than silently repaired. The most consequential is the code for **Clean public areas, facilities and equipment**: Section 1 lists `TRS5123115`, while the detailed unit header prints `TRS512309115`. The package uses `TRS5123115` as the canonical qualification-membership/retrieval code and preserves the detailed-header code in the unit record and `source-fidelity.yaml`.

Other documented issues include duplicate PC number `5.4` in `TRS311205`, a missing Range number `4.5` in `500311106`, curriculum numbering/wording inconsistencies, and probable source typos such as “Drying cleaning machine.”

## Resolver contract — `semantic-index-v1`

1. `field` + `value` means recursively find a **unique mapping or sequence item whose direct field matches**.
2. `kind: yaml_path` means follow the exact dot-separated mapping path.
3. No selector means the full canonical file is the target.
4. Multiple matches are an error.
5. Missing matches are an error.
6. Never silently select the first match.
7. If `fidelity_ref` or `fidelity_refs` exists and the task is source-sensitive, regulatory, assessment-related, or asks for exact TESDA basis, retrieve the matching `source-fidelity.yaml` record too.

Element and performance-criterion records carry unique `element_id` and `pc_id` values so they can be resolved deterministically even when TESDA duplicates a printed criterion number.

## Recommended Module Builder / RAG flow

```text
module need
   ↓
semantic-index.jsonl
   ↓
relevant competency unit / element / PC
   +
matching curriculum entry
   +
source-fidelity record when applicable
   ↓
small context sent to the LLM
   ↓
instructional output with TESDA basis/provenance
```

Do not normally send the entire PDF to a small model. Retrieve only the semantic fragment needed. For regulatory verification, ambiguity, or exact source wording, consult the official TESDA PDF.

## Fidelity boundary

Normalization includes whitespace cleanup, conversion of visual tables to mappings/sequences, semantic grouping of resource-table items, and deterministic identifiers. It does **not** claim literal page-layout reproduction. Historical TESDA terminology and requirements are preserved; apparent errors are not silently modernized or corrected.

There are **no placeholder or pending-work records** in this package.
