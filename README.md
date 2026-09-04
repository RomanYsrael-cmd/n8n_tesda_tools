# TESDA Academic Tools

This repository contains independent academic tools behind one local launcher.
The launcher owns the web entry point, shared static files, Docker stack, and
tool-selection page. Each tool keeps its own schemas, prompts, job logic,
templates, and tests.

## Start locally

Install and start Docker Desktop, then run the launcher from the repository
root:

- Windows: double-click `start.bat`
- macOS/Linux: run `chmod +x start.sh` once, then `./start.sh`

Open <http://localhost:8080> and choose a tool.

## Layout

```text
launcher/                 Shared entry point and tool registry
module_builder/           Module Builder domain package
CBLM_builder(non-quali)/  CBLM Builder domain package
resources/                Reference corpus; not loaded by the runtime
docker-compose.yml        Shared local services
start.bat / start.sh      Repository-level launchers
```

To add another tool, give it an independent FastAPI `APIRouter`, templates,
schemas, storage, and tests, then register its router and menu card in
`launcher/main.py`. A tool must not import another tool's domain models.
