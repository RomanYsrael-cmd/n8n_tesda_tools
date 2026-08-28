# Bookkeeping NC III — Indexed TESDA Training Regulation

This folder is the human-, machine-, and AI-readable **semantic representation** of the TESDA **Bookkeeping NC III** Training Regulations promulgated in November 2007.

The package has **complete semantic coverage** of the qualification, but it is **not a verbatim regulatory transcription**. The official TESDA PDF remains the authoritative regulatory source.

## Representation Layers

Keep these layers separate:

1. **TESDA source** — the official PDF; authoritative for regulatory/source verification.
2. **Normalized semantic representation** — the YAML/Markdown files in this folder; optimized for deterministic retrieval, n8n, RAG, and module generation.
3. **Source-fidelity layer** — `source-fidelity.yaml`; records fidelity-sensitive details, expanded source-derived assessment instructions, and known source anomalies alongside their normalized interpretation.
4. **Instructional interpretation** — generated downstream by the Module Builder; it must not silently rewrite the regulatory index.

This separation is intentional. Historical terms such as **Income Statement**, **Balance Sheet**, Training Methodology III, and other 2007-era requirements remain regulatory facts even when newer instructional material uses newer terminology.

## Files

| File | Purpose |
|---|---|
| `tr.md` | Human-readable entry point and section map |
| `competencies.yaml` | Normalized competency standards for all 15 Basic/Common/Core units |
| `training-standards.yaml` | Section 3 curriculum, delivery, entry, resources, facilities, trainers and institutional assessment |
| `assessment-certification.yaml` | Normalized representation of all nine Section 4 provisions, with source anomaly handling |
| `competency-map.yaml` | Semantic competency-map relationships |
| `glossary.yaml` | Normalized Definition of Terms, with anomaly references where needed |
| `acknowledgements.yaml` | Normalized experts, validation participants and institutional acknowledgements |
| `source-fidelity.yaml` | Fidelity-sensitive source details, expanded assessment instructions and source anomalies |
| `semantic-index.jsonl` | Lightweight deterministic locator for scripts, n8n and LLM/RAG retrieval |
| `manifest.json` | Coverage, fidelity and retrieval-policy declaration |

## Coverage and Fidelity

`manifest.json` deliberately distinguishes **coverage** from **textual fidelity**:

- `coverage_status: complete`
- `representation_type: semantic_normalized`
- `verbatim_transcription: false`

All 15 competency units, all seven Training Standards subsections, all nine national-assessment provisions, the competency map, glossary and acknowledgements are represented. However, normalization may compress wording, convert visual structures into semantic structures, or omit presentation-only detail.

Evidence Guides are especially important: `competencies.yaml` is optimized for semantic retrieval and may summarize longer assessment instructions. Fidelity-sensitive additions belong in `source-fidelity.yaml`. The `500311112` record, for example, restores the source-derived requirements around varied scenarios, unusual/improbable situations, evidence across disruptions, simulation, and workplace-based walkthroughs.

## Known Source Anomalies

Do not silently correct TESDA source errors. Preserve the anomaly and its normalized interpretation separately.

Current documented examples include:

- Section 4.7's apparent use of **“trainees”** where the intended subject appears to be trainers/assessors; and
- the glossary's **Sales invoice** definition, whose seller/buyer perspective is logically reversed in the source.

The canonical semantic files expose the useful normalized interpretation and link to `source-fidelity.yaml` for the source-sensitive record.

## Retrieval Contract — `semantic-index-v1`

Do not interpret strings such as `file.yaml#CODE` as YAML anchors. `semantic-index.jsonl` uses explicit selectors.

A record with:

```json
{
  "canonical": "competencies.yaml",
  "selector": {
    "field": "unit_code",
    "value": "HCS412304"
  }
}
```

means: load `competencies.yaml` and return the unique mapping whose direct `unit_code` field equals `HCS412304`.

A record with:

```json
{
  "canonical": "training-standards.yaml",
  "selector": {
    "kind": "yaml_path",
    "value": "curriculum_design"
  }
}
```

means: follow the dot-separated mapping path in the YAML document.

Resolver rules:

1. `field` + `value` selectors search mappings/sequence items for a unique direct-field match.
2. `kind: yaml_path` follows an exact dot-separated mapping path.
3. A missing selector means the entire canonical file is the retrieval target.
4. Multiple matches for a selector are an error; never choose one silently.
5. If the selected index record has `fidelity_ref`, retrieve the matching record from `source-fidelity.yaml` whenever the task is regulatory, assessment-sensitive, or asks for source fidelity.

## Recommended Module-Builder Retrieval

```text
User/module need
      ↓
semantic-index.jsonl
      ↓
canonical YAML + explicit selector
      ↓
matching source-fidelity record, if any
      ↓
small context sent to the LLM
      ↓
instructional output with TESDA basis/provenance
```

For ordinary module generation, do not send the entire 71-page PDF to the model. For regulatory verification, unresolved ambiguity, or exact-source questions, consult the official TESDA PDF.

There are no placeholder or pending-transcription sections in this package. That statement refers to **semantic coverage**, not verbatim textual reproduction.
