from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import ensure_secret, settings
from .database import Database
from .extraction import extract_syllabus, renumber
from .prompts import manual_refinement_prompt, master_prompt, repair_prompt
from .providers import OpenAICompatibleProvider, strip_markdown_fences
from .schemas import JobStatus, NormalizedSyllabus, ProviderConfig, WeekPlan
from .services import GenerationService, build_imported, validate_imported
from .storage import ensure_layout, job_dir, new_job_id, sanitize_filename, transition
from .validation import template_compatibility

BASE = Path(__file__).resolve().parent.parent
ensure_layout(settings.data_root)
db = Database(settings.data_root / "module-builder.sqlite3")
db.migrate()
db.recover_interrupted()
if db.get_setting("template_path") and Path(db.get_setting("template_path")).exists():
    settings.template = Path(db.get_setting("template_path"))
fernet = Fernet(ensure_secret(settings.data_root))


def provider_config(masked: bool = False) -> ProviderConfig:
    raw = db.get_setting("provider")
    if not raw:
        return ProviderConfig()
    value = json.loads(raw)
    if value.get("api_key"):
        value["api_key"] = fernet.decrypt(value["api_key"].encode()).decode()
    config = ProviderConfig.model_validate(value)
    if masked and config.api_key:
        config.api_key = "••••••••" + config.api_key[-4:]
    return config


def make_provider() -> OpenAICompatibleProvider:
    cfg = provider_config()
    return OpenAICompatibleProvider(cfg.base_url, cfg.api_key, cfg.model)


generation = GenerationService(settings, db, make_provider, lambda: provider_config().semantic_validation)
app = FastAPI(title="TESDA Module Builder", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


@app.get("/health")
def health():
    template_errors = template_compatibility(settings.template) if settings.template.exists() else ["Template file not found"]
    return {"status": "ok" if not template_errors else "needs_setup", "database": "ok", "template": "ok" if not template_errors else template_errors, "data_root": str(settings.data_root)}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    jobs = db.list_jobs()
    grouped = {"Inbox": [], "In Progress": [], "Success": [], "Finished": []}
    for job in jobs:
        status = JobStatus(job["status"])
        if status in {JobStatus.INBOX, JobStatus.NORMALIZING, JobStatus.REVIEW}:
            grouped["Inbox"].append(job)
        elif status in {JobStatus.SUCCESS}:
            grouped["Success"].append(job)
        elif status == JobStatus.FINISHED:
            grouped["Finished"].append(job)
        else:
            grouped["In Progress"].append(job)
    return templates.TemplateResponse(request, "dashboard.html", {"groups": grouped, "configured": bool(db.get_setting("setup_complete"))})


@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    return templates.TemplateResponse(request, "setup.html", {"config": provider_config(masked=True), "template": settings.template, "data_root": settings.data_root, "template_errors": template_compatibility(settings.template) if settings.template.exists() else ["File not found"]})


@app.post("/setup")
async def save_setup(provider: str = Form("openrouter"), base_url: str = Form(...), model: str = Form(...), api_key: str = Form(""), semantic_validation: bool = Form(False), default_author: str = Form(""), default_trainer: str = Form(""), font_family: str = Form("Times New Roman"), font_size: float = Form(12), template_file: UploadFile | None = File(None)):
    existing = provider_config()
    if api_key.startswith("••••"):
        api_key = existing.api_key
    config = ProviderConfig(provider=provider, base_url=base_url, model=model, api_key=api_key, semantic_validation=semantic_validation, default_author=default_author, default_trainer=default_trainer, font_family=font_family, font_size=font_size)
    stored = config.model_dump()
    stored["api_key"] = fernet.encrypt(api_key.encode()).decode() if api_key else ""
    db.set_setting("provider", json.dumps(stored))
    if template_file and template_file.filename:
        if Path(template_file.filename).suffix.lower() != ".docx":
            raise HTTPException(400, "The template must be a DOCX file")
        template_dir = settings.data_root / "Templates"
        template_dir.mkdir(parents=True, exist_ok=True)
        selected = template_dir / "Module Template.docx"
        selected.write_bytes(await template_file.read())
        missing = template_compatibility(selected)
        if missing:
            selected.unlink(missing_ok=True)
            raise HTTPException(400, "Template is missing required placeholders: " + ", ".join(missing))
        settings.template = selected
        db.set_setting("template_path", str(selected))
    db.set_setting("setup_complete", "true")
    return RedirectResponse("/", status_code=303)


@app.post("/api/provider/test")
async def test_provider(base_url: str = Form(...), model: str = Form(...), api_key: str = Form("")):
    if api_key.startswith("••••"):
        api_key = provider_config().api_key
    ok, message = await OpenAICompatibleProvider(base_url, api_key, model).test()
    return JSONResponse({"ok": ok, "message": message}, status_code=200 if ok else 400)


async def normalize_job(job_id: str, path: Path):
    try:
        db.update_job(job_id, status=JobStatus.NORMALIZING, progress=10, message="Reading syllabus structure")
        plan = await asyncio.to_thread(extract_syllabus, path)
        defaults = provider_config()
        if defaults.default_author:
            plan.course.author = defaults.default_author
        if defaults.default_trainer:
            plan.course.trainer = defaults.default_trainer
        plan.course.font_family = defaults.font_family
        plan.course.font_size = defaults.font_size
        out = job_dir(settings.data_root, job_id, JobStatus.INBOX) / "normalized-syllabus.json"
        out.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        db.update_job(job_id, status=JobStatus.REVIEW, progress=100, message="Ready for your review", normalized_json=plan.model_dump_json())
    except Exception as exc:
        db.update_job(job_id, status=JobStatus.FAILED, error=str(exc), message="Syllabus extraction failed")


async def dispatch_n8n(action: str, job_id: str):
    if not settings.use_n8n or not settings.n8n_webhook_base:
        if action == "normalize":
            row = require_job(job_id)
            source = next(job_dir(settings.data_root, job_id, JobStatus(row["status"])).glob("*.docx"))
            await normalize_job(job_id, source)
        else:
            generation.start(job_id)
        return
    url = settings.n8n_webhook_base.rstrip("/") + f"/tesda-module-builder/{action}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json={"job_id": job_id})
        response.raise_for_status()


@app.post("/upload")
async def upload(background: BackgroundTasks, files: list[UploadFile] = File(...)):
    ids = []
    for file in files:
        if Path(file.filename or "").suffix.lower() != ".docx":
            raise HTTPException(400, "Only DOCX syllabus files are accepted")
        content = await file.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(400, "Each syllabus must be 25 MB or smaller")
        if not content.startswith(b"PK"):
            raise HTTPException(400, f"{file.filename} is not a valid DOCX package")
        job_id = new_job_id()
        name = sanitize_filename(file.filename or "syllabus.docx")
        folder = job_dir(settings.data_root, job_id, JobStatus.INBOX)
        folder.mkdir(parents=True)
        path = folder / name
        path.write_bytes(content)
        db.create_job(job_id, name)
        background.add_task(dispatch_n8n, "normalize", job_id)
        ids.append(job_id)
    return RedirectResponse(f"/jobs/{ids[0]}", status_code=303)


def require_job(job_id: str):
    row = db.get_job(job_id)
    if not row:
        raise HTTPException(404, "Job not found")
    return row


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(request: Request, job_id: str):
    job = require_job(job_id)
    status = JobStatus(job["status"])
    if status in {JobStatus.INBOX, JobStatus.NORMALIZING, JobStatus.GENERATING}:
        target = "progress"
    elif status == JobStatus.REVIEW:
        target = "plan"
    elif status in {JobStatus.SUCCESS, JobStatus.FINISHED}:
        target = "result"
    else:
        active_folder = job_dir(settings.data_root, job_id, status)
        target = "manual/quality" if (active_folder / "refinement-prompt.txt").exists() else "mode"
    return RedirectResponse(f"/jobs/{job_id}/{target}", status_code=303)


def job_context(request: Request, job_id: str) -> dict:
    job = require_job(job_id)
    plan = NormalizedSyllabus.model_validate_json(job["normalized_json"]) if job.get("normalized_json") else None
    stages = db.stages(job_id)
    folder = job_dir(settings.data_root, job_id, JobStatus(job["status"])) / "modules"
    modules = sorted(p.name for p in folder.glob("*.docx")) if folder.exists() else []
    return {"request": request, "job": job, "plan": plan, "stages": stages, "modules": modules,
            "call_estimate": len([w for w in plan.weeks if w.generate]) * 4 if plan else 0}


@app.get("/jobs/{job_id}/plan", response_class=HTMLResponse)
def plan_page(request: Request, job_id: str):
    return templates.TemplateResponse(request, "job_plan.html", job_context(request, job_id))


@app.get("/jobs/{job_id}/mode", response_class=HTMLResponse)
def mode_page(request: Request, job_id: str):
    return templates.TemplateResponse(request, "job_mode.html", job_context(request, job_id))


@app.get("/jobs/{job_id}/manual/initial", response_class=HTMLResponse)
def manual_initial_page(request: Request, job_id: str, import_error: str = ""):
    context = job_context(request, job_id)
    folder = job_dir(settings.data_root, job_id, JobStatus(context["job"]["status"]))
    repair = folder / "repair-prompt.txt"
    refinement = folder / "refinement-prompt.txt"
    if refinement.exists():
        return RedirectResponse(f"/jobs/{job_id}/manual/quality", 303)
    context.update({"prompt": repair.read_text(encoding="utf-8") if repair.exists() else master_prompt(context["plan"], settings.quiz_questions),
                    "is_repair": repair.exists(), "import_error": import_error})
    return templates.TemplateResponse(request, "job_manual_initial.html", context)


@app.get("/jobs/{job_id}/manual/quality", response_class=HTMLResponse)
def manual_quality_page(request: Request, job_id: str, import_error: str = ""):
    context = job_context(request, job_id)
    folder = job_dir(settings.data_root, job_id, JobStatus(context["job"]["status"]))
    refinement = folder / "refinement-prompt.txt"
    if not refinement.exists():
        return RedirectResponse(f"/jobs/{job_id}/manual/initial", 303)
    repair = folder / "repair-prompt.txt"
    context.update({"prompt": repair.read_text(encoding="utf-8") if repair.exists() else refinement.read_text(encoding="utf-8"),
                    "is_repair": repair.exists(), "import_error": import_error})
    return templates.TemplateResponse(request, "job_manual_quality.html", context)


@app.get("/jobs/{job_id}/progress", response_class=HTMLResponse)
def progress_page(request: Request, job_id: str):
    return templates.TemplateResponse(request, "job_progress.html", job_context(request, job_id))


@app.get("/jobs/{job_id}/result", response_class=HTMLResponse)
def result_page(request: Request, job_id: str):
    return templates.TemplateResponse(request, "job_result.html", job_context(request, job_id))


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return {"job": require_job(job_id), "stages": db.stages(job_id)}


@app.post("/api/n8n/dispatch/{action}/{job_id}")
async def n8n_dispatch(action: str, job_id: str):
    """Internal Docker-network callback used by the versioned n8n workflows."""
    job = require_job(job_id)
    if action == "normalize":
        source = next(job_dir(settings.data_root, job_id, JobStatus(job["status"])).glob("*.docx"), None)
        if not source:
            raise HTTPException(404, "Uploaded syllabus not found")
        asyncio.create_task(normalize_job(job_id, source))
    elif action in {"generate", "retry"}:
        generation.start(job_id)
    elif action == "build-import":
        raise HTTPException(400, "Imported content must be submitted to the application import endpoint")
    else:
        raise HTTPException(404, "Unknown workflow action")
    return {"accepted": True, "job_id": job_id, "action": action}


@app.post("/api/n8n/error/{job_id}")
async def n8n_error(job_id: str, request: Request):
    require_job(job_id)
    payload = await request.json()
    message = str(payload.get("message", "n8n workflow failed"))[:1000]
    db.update_job(job_id, status=JobStatus.FAILED, error=message, message="Workflow reported an error")
    return {"received": True}


@app.post("/api/n8n/build-import/{job_id}")
async def n8n_build_import(job_id: str, request: Request):
    require_job(job_id)
    raw = await request.json()
    ok, errors = await asyncio.to_thread(build_imported, settings, db, job_id, raw)
    return JSONResponse({"ok": ok, "errors": errors}, status_code=200 if ok else 422)


@app.post("/jobs/{job_id}/review")
async def update_review(request: Request, job_id: str):
    job = require_job(job_id)
    plan = NormalizedSyllabus.model_validate_json(job["normalized_json"])
    form = await request.form()
    plan.course.code = str(form.get("course_code", plan.course.code))
    plan.course.title = str(form.get("course_title", plan.course.title))
    plan.course.author = str(form.get("author", plan.course.author))
    plan.course.trainer = str(form.get("trainer", plan.course.trainer))
    plan.course.font_family = str(form.get("font_family", plan.course.font_family))
    plan.course.font_size = float(form.get("font_size", plan.course.font_size))
    for week in plan.weeks:
        prefix = f"week_{week.actual_week}_"
        week.generate = form.get(prefix + "generate") == "on"
        week.proposed_title = str(form.get(prefix + "title", week.proposed_title))
        week.topic_scope = str(form.get(prefix + "scope", week.topic_scope))
        week.learning_outcome = str(form.get(prefix + "outcome", week.learning_outcome))
    plan.weeks = renumber(plan.weeks)
    plan = NormalizedSyllabus.model_validate(plan.model_dump())
    serialized = plan.model_dump_json()
    (job_dir(settings.data_root, job_id, JobStatus.REVIEW) / "normalized-syllabus.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    db.update_job(job_id, normalized_json=serialized, message="Review changes saved")
    return RedirectResponse(f"/jobs/{job_id}/plan", status_code=303)


@app.post("/jobs/{job_id}/approve")
def approve(job_id: str):
    job = require_job(job_id)
    status = JobStatus(job["status"])
    if status != JobStatus.REVIEW:
        raise HTTPException(409, "Job is not awaiting review")
    transition(settings.data_root, job_id, status, JobStatus.APPROVED)
    db.update_job(job_id, status=JobStatus.APPROVED, message="Approved. Choose automatic or manual mode")
    return RedirectResponse(f"/jobs/{job_id}/mode", status_code=303)


@app.post("/jobs/{job_id}/generate")
async def generate(job_id: str):
    job = require_job(job_id)
    if JobStatus(job["status"]) not in {JobStatus.APPROVED, JobStatus.FAILED, JobStatus.PAUSED, JobStatus.CANCELLED}:
        raise HTTPException(409, "This job cannot start automatic generation now")
    await dispatch_n8n("generate", job_id)
    return RedirectResponse(f"/jobs/{job_id}/progress", status_code=303)


@app.post("/jobs/{job_id}/pause")
def pause(job_id: str):
    require_job(job_id); db.set_control(job_id, pause=True); return RedirectResponse(f"/jobs/{job_id}/progress", 303)


@app.post("/jobs/{job_id}/cancel")
def cancel(job_id: str):
    require_job(job_id); db.set_control(job_id, cancel=True); return RedirectResponse(f"/jobs/{job_id}/progress", 303)


@app.post("/jobs/{job_id}/resume")
async def resume(job_id: str):
    require_job(job_id); await dispatch_n8n("generate", job_id); return RedirectResponse(f"/jobs/{job_id}/progress", 303)


@app.post("/jobs/{job_id}/retry-module/{lesson_number}")
async def retry_module(job_id: str, lesson_number: int):
    job = require_job(job_id)
    plan = NormalizedSyllabus.model_validate_json(job["normalized_json"])
    week = next((w for w in plan.weeks if w.lesson_number == lesson_number), None)
    if not week:
        raise HTTPException(404, "Lesson not found")
    db.clear_module_stages(job_id, lesson_number)
    folder = job_dir(settings.data_root, job_id, JobStatus(job["status"])) / "modules"
    for path in folder.glob(f"Week {week.actual_week:02d} - Lesson {lesson_number:02d} - *.docx") if folder.exists() else []:
        path.unlink()
    await dispatch_n8n("generate", job_id)
    return RedirectResponse(f"/jobs/{job_id}/progress", 303)


@app.post("/jobs/{job_id}/import")
async def import_json(job_id: str, pasted_json: str = Form(""), json_file: UploadFile | None = File(None)):
    require_job(job_id)
    text = pasted_json
    if json_file and json_file.filename:
        text = (await json_file.read()).decode("utf-8-sig")
    try:
        raw = json.loads(strip_markdown_fences(text))
    except json.JSONDecodeError as exc:
        return RedirectResponse(f"/jobs/{job_id}/manual/initial?import_error=Invalid+JSON+at+line+{exc.lineno}", 303)
    bundles, errors = await asyncio.to_thread(validate_imported, settings, db, job_id, raw)
    if errors:
        repair = repair_prompt(errors, raw)
        folder = job_dir(settings.data_root, job_id, JobStatus(db.get_job(job_id)["status"]))
        (folder / "repair-prompt.txt").write_text(repair, encoding="utf-8")
        (folder / "rejected-import.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        db.update_job(job_id, message="Imported JSON needs correction", error="; ".join(errors))
    else:
        job = require_job(job_id)
        plan = NormalizedSyllabus.model_validate_json(job["normalized_json"])
        folder = job_dir(settings.data_root, job_id, JobStatus(job["status"]))
        (folder / "pending-manual.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        (folder / "refinement-prompt.txt").write_text(manual_refinement_prompt(plan, bundles), encoding="utf-8")
        (folder / "repair-prompt.txt").unlink(missing_ok=True)
        (folder / "rejected-import.json").unlink(missing_ok=True)
        db.update_job(job_id, mode="manual", message="Initial JSON is valid. Run the refinement prompt, then import the refined JSON", error="")
    return RedirectResponse(f"/jobs/{job_id}/manual/quality" if not errors else f"/jobs/{job_id}/manual/initial", 303)


@app.post("/jobs/{job_id}/import-refined")
async def import_refined_json(job_id: str, pasted_json: str = Form(""), json_file: UploadFile | None = File(None)):
    require_job(job_id)
    text = pasted_json
    if json_file and json_file.filename:
        text = (await json_file.read()).decode("utf-8-sig")
    try:
        raw = json.loads(strip_markdown_fences(text))
    except json.JSONDecodeError as exc:
        return RedirectResponse(f"/jobs/{job_id}/manual/quality?import_error=Invalid+JSON+at+line+{exc.lineno}", 303)
    ok, errors = await asyncio.to_thread(build_imported, settings, db, job_id, raw)
    if not ok:
        job = require_job(job_id)
        folder = job_dir(settings.data_root, job_id, JobStatus(job["status"]))
        (folder / "repair-prompt.txt").write_text(repair_prompt(errors, raw), encoding="utf-8")
        (folder / "rejected-import.json").write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")
        db.update_job(job_id, message="Refined JSON needs correction", error="; ".join(errors))
    return RedirectResponse(f"/jobs/{job_id}/result" if ok else f"/jobs/{job_id}/manual/quality", 303)


@app.post("/jobs/{job_id}/repair-import")
async def repair_import(job_id: str):
    job = require_job(job_id)
    folder = job_dir(settings.data_root, job_id, JobStatus(job["status"]))
    rejected_path = folder / "rejected-import.json"
    repair_path = folder / "repair-prompt.txt"
    if not rejected_path.exists() or not repair_path.exists():
        raise HTTPException(404, "No rejected import is available for repair")
    repaired = await make_provider().complete_json(repair_path.read_text(encoding="utf-8"), max_attempts=3)
    ok, errors = await asyncio.to_thread(build_imported, settings, db, job_id, repaired)
    if not ok:
        repair_path.write_text(repair_prompt(errors, repaired), encoding="utf-8")
        rejected_path.write_text(json.dumps(repaired, indent=2, ensure_ascii=False), encoding="utf-8")
        db.update_job(job_id, error="; ".join(errors), message="API repair still needs correction")
    return RedirectResponse(f"/jobs/{job_id}", 303)


@app.get("/jobs/{job_id}/prompt.txt")
def prompt_download(job_id: str):
    job = require_job(job_id)
    plan = NormalizedSyllabus.model_validate_json(job["normalized_json"])
    path = settings.data_root / "JSON Dump" / "Success" / f"{job_id}-master-prompt.txt"
    path.write_text(master_prompt(plan, settings.quiz_questions), encoding="utf-8")
    return FileResponse(path, filename=f"{job_id}-ChatGPT-prompt.txt")


@app.get("/jobs/{job_id}/download/{name}")
def download(job_id: str, name: str):
    job = require_job(job_id)
    if name not in {"course-modules.zip", "normalized-syllabus.json", "validation-report.json", "generation-report.json", "repair-prompt.txt", "refinement-prompt.txt"}:
        raise HTTPException(400, "Unsupported download")
    path = job_dir(settings.data_root, job_id, JobStatus(job["status"])) / name
    if not path.exists():
        raise HTTPException(404, "File not ready")
    return FileResponse(path, filename=path.name)


@app.get("/jobs/{job_id}/modules/{filename}")
def download_module(job_id: str, filename: str):
    job = require_job(job_id)
    if Path(filename).name != filename or not filename.lower().endswith(".docx"):
        raise HTTPException(400, "Invalid module filename")
    path = job_dir(settings.data_root, job_id, JobStatus(job["status"])) / "modules" / filename
    if not path.exists():
        raise HTTPException(404, "Module not found")
    return FileResponse(path, filename=filename)


@app.post("/jobs/{job_id}/archive")
def archive(job_id: str):
    job = require_job(job_id)
    if JobStatus(job["status"]) != JobStatus.SUCCESS:
        raise HTTPException(409, "Only successful jobs can be archived")
    transition(settings.data_root, job_id, JobStatus.SUCCESS, JobStatus.FINISHED)
    db.update_job(job_id, status=JobStatus.FINISHED, message="Archived")
    return RedirectResponse("/", 303)
