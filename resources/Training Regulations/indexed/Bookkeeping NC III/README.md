# Bookkeeping NC III — Complete Indexed TESDA Training Regulation

This folder is the human-, machine-, and AI-readable semantic representation of the complete TESDA **Bookkeeping NC III** Training Regulations promulgated in November 2007.

The original TESDA PDF remains the authoritative regulatory source. This package normalizes its structure for reliable retrieval; it is not intended to replace the source PDF as a legal/regulatory artifact.

## Files

| File | Purpose |
|---|---|
| `tr.md` | Human-readable entry point and complete section map |
| `competencies.yaml` | All 15 Basic/Common/Core competency standards |
| `training-standards.yaml` | Section 3 curriculum, delivery, entry, resources, facilities, trainers and institutional assessment |
| `assessment-certification.yaml` | All nine Section 4 national assessment/certification provisions |
| `competency-map.yaml` | Complete semantic competency map |
| `glossary.yaml` | Complete normalized Definition of Terms |
| `acknowledgements.yaml` | Technical experts, validation participants and institutional acknowledgements |
| `semantic-index.jsonl` | Lightweight lookup index for scripts, n8n and LLM/RAG retrieval |
| `manifest.json` | Coverage declaration and package metadata |

## Retrieval Pattern

Do not send the entire Training Regulation to an LLM for ordinary module-generation tasks.

1. Search `semantic-index.jsonl` by unit code, title, competency group or section.
2. Follow the matching record's `canonical` reference.
3. Load only the relevant structured record.
4. Combine `competencies.yaml` with `training-standards.yaml` when generating training/module content.
5. Consult the original TESDA PDF for source verification where required.

Example:

```text
Need: Prepare Financial Reports
Lookup: HCS412304
Competency standard: competencies.yaml
Training outcomes/methodology/assessment: training-standards.yaml
```

## Source Fidelity

This package preserves the **2007** regulation semantically. It does not silently replace historical terms or requirements with current TESDA practice. For example, it retains Training Methodology III, the stated 292-hour curriculum, legacy computer/storage references, the original national-assessment arrangements, and source wording that may appear unusual.

Blank values in a TESDA source table remain blank rather than being guessed. That is source fidelity, not an incomplete transcription.

## Completeness

`manifest.json` is the machine-readable coverage declaration. It records full representation of:

- Section 1 qualification and competency requirements;
- Section 2 competency standards for all 15 units, including descriptors, elements, performance criteria, ranges of variables and evidence guides;
- all seven Section 3 Training Standards subsections;
- all nine Section 4 assessment/certification provisions;
- the Competency Map;
- Definition of Terms; and
- Acknowledgements and validation participants.

There are no placeholder or pending-transcription sections.
