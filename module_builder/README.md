# TESDA Module Builder

Turn a Word syllabus into reviewed, validated TESDA learning modules from a simple local web page. Your syllabi, generated modules, settings, and job history stay in a folder on your own computer. n8n is included as the separate workflow orchestrator, but normal use does not require opening its editor.

## The easy way to start

You need **Docker Desktop**. Install it, open it, and wait until it says it is running.

### Windows

Double-click `start.bat`. When the browser opens, use **Setup** and follow the page.

### macOS or Linux

Open a terminal in this folder once, run `chmod +x start.sh`, then run `./start.sh`. Open <http://localhost:8080> if the browser does not open automatically.

To stop the tool, run:

```text
docker compose down
```

Stopping does not erase your work. Jobs and settings are kept in a Docker-managed persistent volume by default, so they survive restarts and upgrades.

## First-time setup

1. Open **Setup**.
2. Keep OpenRouter selected, or enter any OpenAI-compatible service.
3. Enter the base URL, model ID, and your own API key. The default model is `openrouter/free`.
4. Choose **Test connection**.
5. Optionally upload a replacement `.docx` template. The app checks it before accepting it.
6. Choose **Finish setup**.

The repaired `template/Module Template.docx` is selected automatically and checked for all required placeholders. API keys are encrypted using a secret created under the local data folder. Saved keys are masked in the browser and are excluded from JSON dumps and n8n payloads.

Common compatible services include OpenRouter, Ollama, LM Studio, Groq, and Together. For Ollama or LM Studio, use the OpenAI-compatible URL they show and leave the API key blank if that local server does not require one.

## Build a course

1. On the dashboard, choose one or more `.docx` syllabus files.
2. Wait while the syllabus is read. The page updates automatically.
3. Check the course details and every week. You can edit titles, scope, outcomes, and whether a module should be made.
4. Orientation and examination weeks begin turned off. Generated lessons are numbered continuously across skipped weeks.
5. Choose **Approve this plan**.
6. Choose a mode:
   - **Automatic API:** about three model requests for each module, plus bounded repairs when returned JSON is invalid. A request estimate is shown first.
   - **Manual ChatGPT JSON:** copy or download the deterministic prompt, use it in ChatGPT, then paste or upload the JSON. This mode makes no generation calls. Invalid JSON produces an exact repair prompt you can use repeatedly.
7. Watch each module and stage. You may pause after the current module, cancel remaining work, or retry/resume a failed job.
8. Download the ZIP when the job moves to **Success**. Archive it when you want it moved to **Finished**.

Successful course folders contain:

```text
Success/<job-id>/
  modules/Week NN - Lesson NN - Title.docx
  normalized-syllabus.json
  validation-report.json
  generation-report.json
  course-modules.zip
```

The data root also contains `Inbox`, `In Progress`, `Success`, `Finished`, `JSON Dump/Success`, and `JSON Dump/Failed`. Partial successful modules remain intact if a later module fails.

## Useful checks and fixes

- App health: <http://localhost:8080/health>
- App logs: `docker compose logs module-builder`
- n8n logs: `docker compose logs n8n`
- If the page does not open, confirm Docker Desktop is running and ports 8080 and 5679 are free.
- The safest cross-platform default uses Docker volumes named `tesda-module-builder-data` and `tesda-module-builder-n8n-data`.
- To expose the data as ordinary folders on your computer, copy `.env.example` to `.env`, change `MODULE_BUILDER_DATA_ROOT`, and start with `docker compose -f docker-compose.yml -f docker-compose.bind.yml up -d --build`. Docker Desktop must be allowed to share that drive/folder.
- Never put a real API key in `.env.example`, workflow JSON, or a file you plan to share.

LibreOffice is installed inside the application image. Each generated DOCX is structurally audited and converted headlessly to PDF as a render check. This detects conversion and page-generation failures; it does not claim human or pixel-perfect semantic review.

## n8n workflows

Version-controlled exports are under `workflows`:

- normalization acknowledgment and dispatch
- automatic-generation acknowledgment and dispatch
- build-from-imported-JSON dispatch
- error callback

The application is complete without manually drawing workflows. On startup, a short-lived initializer imports and publishes the bundled workflows idempotently; rerunning it does not create duplicates. Normal users never need to open the n8n editor. The included, isolated n8n service is available at <http://localhost:5679> for troubleshooting only. Port 5679 is used so an existing user-owned n8n installation on the usual port 5678 is not disturbed.

The app sends only job identifiers and callback URLs to n8n. Provider API keys remain encrypted inside Module Builder and never enter n8n workflow payloads or logs.

## Developer architecture

`app/main.py` owns HTTP/UI routes; `database.py` and `001_initial.sql` define the SQLite WAL job store and initial migration; `storage.py` owns lifecycle folders; `extraction.py` converts varied DOCX layouts into stable source-traceable plans; `schemas.py` is the Pydantic contract; `providers.py` is the OpenAI-compatible adapter; `prompts.py` contains deterministic prompts; `services.py` runs restart-safe generation/import jobs; `docx_engine.py` fills the repaired template deterministically; and `validation.py` owns schema, cross-field, package, placeholder, and LibreOffice checks.

The boundaries are intentionally reusable without creating a shared monolith. A future academic tool can copy the small patterns for encrypted local settings, SQLite job/stage records, lifecycle folders, provider adapters, and Docker launch helpers, while keeping its own schemas, prompts, UI, and workflows. Do not import Module Builder domain models into another tool.

Run tests from this folder with Python 3.12 and the development dependencies:

```text
python -m pip install -e ".[dev]"
python -m pytest
```

The AE17 smoke test uses mocked module JSON and requires no paid model call. It verifies the requested 13 generated instructional weeks, deterministic lesson numbering, template filling, output layout, reports, and ZIP packaging.

## Current MVP boundaries

- The normalizer is deterministic and tuned for Word tables with explicit week labels. Unusual scanned documents or schedules made only from images need manual review or conversion to editable DOCX text.
- Semantic validation is optional because it costs one model call and can itself be unreliable on free models. Deterministic validation always runs.
- Automatic render verification proves LibreOffice can open and convert the file; a teacher should still review instructional quality and final pagination before distribution.
- Direct adapters for non-OpenAI-compatible providers can be added behind the provider interface later.
