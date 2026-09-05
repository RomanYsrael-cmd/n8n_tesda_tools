# TESDA Training Regulation Index — Housekeeping NC II

## Qualification

**Housekeeping NC II** is a Tourism Sector (Hotel and Restaurant) qualification covering the competencies required to prepare guest rooms; clean public areas, facilities and equipment; provide housekeeping and valet/butler services; launder linen and guest clothes; and deal with/handle intoxicated guests.

- **Level:** NC II
- **Revision:** Amended
- **Promulgated:** December 2013
- **Lifecycle:** Current, verified 2026-09-02 against TESDA's current Training Regulations portal
- **Official PDF:** `https://www.tesda.gov.ph/Downloadables/TR%20Housekeeping%20NC%20II.pdf`
- **Nominal duration:** 18 hours Basic + 18 hours Common + 400 hours Core = **436 hours**

> This package has complete semantic coverage but is not a verbatim regulatory transcription. The official TESDA PDF remains authoritative.

## Occupational outcomes listed by TESDA

Junior Cleaner; Assistant Cleaner; Assistant Public Area Cleaner; Cleaner; Public Area Cleaner; Attendant; Room/Cabin Attendant/Room Maid; Laundry Attendant; Housekeeping Attendant; Butler.

## Competencies

### Basic — 4 units

- `500311105` — Participate in workplace communication
- `500311106` — Work in team environment
- `500311107` — Practice career professionalism
- `500311108` — Practice occupational health and safety procedures

### Common — 5 units

- `TRS311201` — Develop and update industry knowledge
- `TRS311202` — Observe workplace hygiene procedures
- `TRS311203` — Perform computer operations
- `TRS311204` — Perform workplace and safety practices
- `TRS311205` — Provide effective customer service

### Core — 6 units

- `TRS5123111` — Provide housekeeping services to guests
- `TRS5123112` — Clean and prepare rooms for incoming guests
- `TRS5123113` — Provide valet/butler service
- `TRS5123114` — Laundry linen and guest clothes
- `TRS5123115` — Clean public areas, facilities and equipment
- `TRS5123122` — Deal with/Handle intoxicated guests

**Source code warning:** the detailed unit header for “Clean public areas, facilities and equipment” prints `TRS512309115`, while Section 1 lists `TRS5123115`. The canonical package code is the Section 1 qualification-membership code; both forms and the rationale are preserved in `source-fidelity.yaml`.

## Training Standards

Section 3 is represented in `training-standards.yaml`:

- `3.1` Curriculum Design — all 15 unit entries with Learning Outcomes, Methodology and Assessment Approach
- `3.2` Training Delivery — 10 competency-based TVET principles and five listed modalities
- `3.3` Trainee Entry Requirements — English oral/written communication and basic mathematical computation
- `3.4` Tools, Equipment and Materials — full resource list for a maximum of 25 trainees
- `3.5` Training Facilities — 114 sq. m. total workshop area for a 25-trainee intake
- `3.6` Trainer’s Qualifications — National TVET Trainer Certificate I (TM I and NC), physical/mental fitness, and at least two years relevant industry experience
- `3.7` Institutional Assessment — certificate of achievement for each unit of competency

The source does **not** provide per-unit nominal hours. The package therefore leaves each curriculum entry's `nominal_hours` as null instead of inventing allocations.

## National assessment and certification

Section 4 is in `assessment-certification.yaml`. To attain Housekeeping NC II, candidates must demonstrate competence in all units. Assessment focuses on core units, with Basic and Common units integrated or assessed concurrently. TESDA also provides a COC-accumulation pathway across four areas: Providing Butler Service, Providing Housekeeping to Guests, Cleaning public areas, and Providing laundry service.

## Other indexed sections

- Annex A competency map → `competency-map.yaml`
- Definition of Terms (8 entries) → `glossary.yaml`
- Review panel and validation contributors → `acknowledgements.yaml`
- Source anomalies/fidelity-sensitive interpretations → `source-fidelity.yaml`
- Coverage/lifecycle/source declaration → `manifest.json`
- Deterministic retrieval → `semantic-index.jsonl`

## Retrieval behavior

Use `semantic-index.jsonl` rather than pseudo-anchors. A `field`/`value` selector must resolve to exactly one direct-field match. A `yaml_path` selector follows the exact mapping path. Missing or multiple matches are errors. When an index record carries a fidelity reference and the request is regulatory, assessment-sensitive, or source-specific, retrieve the matching fidelity record as well.

For module generation, retrieve the relevant competency fragment plus its curriculum entry, not the whole PDF. For exact-source verification, consult the official TESDA PDF.
