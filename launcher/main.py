from __future__ import annotations

import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.main import make_provider, router as module_builder_router, settings


LAUNCHER_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = LAUNCHER_ROOT.parent


@dataclass(frozen=True)
class ToolCard:
    slug: str
    title: str
    description: str
    href: str


app = FastAPI(title="TESDA Academic Tools", version="0.1.0")
app.mount("/static", StaticFiles(directory=LAUNCHER_ROOT / "static"), name="static")
templates = Jinja2Templates(directory=LAUNCHER_ROOT / "templates")

tools: list[ToolCard] = []

if os.getenv("TESDA_DEPLOYMENT_MODE", "local").lower() == "saas":
    from saas.router import install_saas

    install_saas(app)


def register_tool(card: ToolCard, router) -> None:
    """Register one independent tool and expose it on the launcher menu."""
    app.include_router(router)
    tools.append(card)


if os.getenv("TESDA_DEPLOYMENT_MODE", "local").lower() != "saas":
    register_tool(
        ToolCard("module-builder", "Module Builder", "Create course modules from a syllabus.", "/module-builder"),
        module_builder_router,
    )

CBLM_PACKAGE_ROOT = REPOSITORY_ROOT / "CBLM_builder(non-quali)"
if not CBLM_PACKAGE_ROOT.exists():
    CBLM_PACKAGE_ROOT = Path("/cblm")
if CBLM_PACKAGE_ROOT.exists() and os.getenv("TESDA_DEPLOYMENT_MODE", "local").lower() != "saas":
    sys.path.insert(0, str(CBLM_PACKAGE_ROOT))
    from cblm_app.router import create_router as create_cblm_router

    register_tool(
        ToolCard("cblm-builder", "CBLM Builder", "Create one complete CBLM for each learning outcome.", "/cblm"),
        create_cblm_router(
            Path(os.getenv("CBLM_BUILDER_DATA_ROOT", str(settings.data_root / "CBLM Builder"))),
            CBLM_PACKAGE_ROOT / "Templates",
            CBLM_PACKAGE_ROOT / "Prompts.xlsx",
            make_provider,
        ),
    )


@app.get("/", response_class=HTMLResponse)
def tool_selector(request: Request):
    if os.getenv("TESDA_DEPLOYMENT_MODE", "local").lower() == "saas":
        return RedirectResponse("/app", status_code=307)
    return templates.TemplateResponse(request, "tool-selector.html", {"tools": [asdict(tool) for tool in tools]})
