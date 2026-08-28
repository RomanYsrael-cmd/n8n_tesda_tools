# Bookkeeping NC III — Complete Indexed TESDA Training Regulation

This folder is the machine-, AI-, and human-readable indexed representation of the TESDA **Bookkeeping NC III** Training Regulations promulgated in November 2007.

## Files

| File | Purpose |
|---|---|
| `tr.md` | Human-readable entry point and complete section map |
| `competencies.yaml` | Canonical structured competency standards for all 15 Basic/Common/Core units |
| `training-standards.yaml` | Complete normalized Section 3 training standards and curriculum |
| `assessment-certification.yaml` | Complete Section 4 national assessment/certification provisions |
| `glossary.yaml` | Complete normalized Definition of Terms |
| `semantic-index.jsonl` | Small retrieval index for scripts, n8n and LLM/RAG lookup |
| `manifest.json` | Coverage declaration and machine-readable package metadata |

## Retrieval pattern

Do not send the entire Training Regulation to an LLM for ordinary module-generation tasks.

1. Search `semantic-index.jsonl` by unit code, title, group or section.
2. Read the `canonical` field returned by the matching record.
3. Load only the matching object from the canonical YAML file.
4. Use the original TESDA PDF when regulatory/source verification is required.

Example:

```text
Need: Prepare Financial Reports
Lookup: unit_code == HCS412304
Index: semantic-index.jsonl
Canonical source: competencies.yaml -> HCS412304
Relevant elements:
  - Prepare financial statements
  - Analyze financial statements
```

For module generation, `training-standards.yaml` supplies the official learning outcomes, methodologies and assessment approaches while `competencies.yaml` supplies the competency standard and evidence requirements.

## Source fidelity

The indexed files preserve the 2007 Training Regulation as a historical regulatory source. Old terminology and requirements are not silently replaced by newer TESDA practices. Examples include Training Methodology III, 2007-era computer/storage-media references, the stated 292-hour nominal duration, and the original assessment arrangements.

Where the source contains wording that appears unusual, the indexed data retains or explicitly notes the source wording instead of guessing a correction.

## Completeness

`manifest.json` records coverage. This package contains no placeholder or pending-transcription sections. All 15 competency units include their descriptor, elements, performance criteria, range of variables and evidence guide, and all regulatory sections needed for qualification, training and assessment retrieval are represented.
