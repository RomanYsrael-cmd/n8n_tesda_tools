# Bookkeeping NC III — Indexed TR Prototype

This folder is a working proof of concept for converting a TESDA Training Regulation into a representation that humans, scripts, n8n workflows, and lightweight LLMs can consume reliably.

## Files

- `tr.md` — canonical TRMD v1 Markdown representation.
- `semantic-index.jsonl` — retrieval-ready semantic records derived from the structure of `tr.md`.

The authoritative source remains the original TESDA Training Regulation PDF. This prototype is deliberately partial: missing regulatory text is marked as pending instead of being guessed.

## Retrieval model

Do not chunk `tr.md` by arbitrary token count. Retrieve by semantic IDs and record types such as:

- training regulation
- occupational outcome
- competency unit
- element
- performance criterion
- required knowledge
- required skill
- range of variable
- evidence guide item
- training duration

As the full transcription is added, each semantic unit should receive a stable ID and its own JSONL record.

## Python example

```python
import json
from pathlib import Path

records = [
    json.loads(line)
    for line in Path("semantic-index.jsonl").read_text(encoding="utf-8").splitlines()
    if line.strip()
]

journalize = [
    item for item in records
    if item.get("unit_code") == "HCS412301"
]

print(journalize)
```

## Lightweight-LLM usage

A Module Builder should first query the index and then provide only the matching Markdown section to the model. For example, a request involving `HCS412301` should retrieve the Journalize Transactions section instead of sending the entire Training Regulation to the model.

A typical flow is:

```text
Module Builder request
        ↓
semantic-index.jsonl
        ↓
find matching semantic IDs
        ↓
retrieve matching section from tr.md
        ↓
small/local LLM
        ↓
generated module with TESDA basis
```

## Prototype status

`prototype_partial` means the structure and indexing approach are ready to test, but the full TESDA source has not yet been transcribed.

`unit_identity_only` means the unit code and title have been indexed, while the unit's elements, performance criteria, range of variables, and evidence guide are still pending transcription.

Production ingestion should preserve TESDA source wording and add page-level provenance and review status for every important semantic record.
