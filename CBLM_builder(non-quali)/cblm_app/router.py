from __future__ import annotations

import asyncio
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .database import CBLMDatabase
from .extraction import extract_cblm_plan
from .schemas import CBLMPlan
from .service import CBLMGenerationService
from .storage import ensure_layout, job_dir, new_job_id, safe_name, transition


def create_router(root: Path, template_dir: Path, prompt_file: Path, provider_factory):
    ensure_layout(root)
    db = CBLMDatabase(root / "cblm-builder.sqlite3"); db.migrate()
    service = CBLMGenerationService(root, template_dir, prompt_file, db, provider_factory)
    web = Jinja2Templates(directory=Path(__file__).parent / "web")
    router = APIRouter(prefix="/cblm")

    def require(job_id):
        row = db.get_job(job_id)
        if not row: raise HTTPException(404, "CBLM job not found")
        return row

    @router.get("", response_class=HTMLResponse)
    def dashboard(request: Request):
        groups = {"Inbox": [], "In Progress": [], "Success": [], "Finished": []}
        for row in db.list_jobs():
            key = "Inbox" if row["status"] in {"inbox","normalizing","review"} else "Success" if row["status"]=="success" else "Finished" if row["status"]=="finished" else "In Progress"
            groups[key].append(row)
        return web.TemplateResponse(request, "dashboard.html", {"groups": groups})

    async def normalize(job_id, path):
        try:
            db.update_job(job_id, status="normalizing", progress=15, message="Reading syllabus")
            plan = await asyncio.to_thread(extract_cblm_plan, path)
            db.update_job(job_id, status="review", progress=100, message="Ready for review", plan_json=plan.model_dump_json())
        except Exception as exc: db.update_job(job_id, status="failed", message="Extraction failed", error=str(exc))

    @router.post("/upload")
    async def upload(background: BackgroundTasks, syllabus: UploadFile = File(...)):
        if Path(syllabus.filename or "").suffix.lower() != ".docx": raise HTTPException(400, "Upload a DOCX syllabus")
        job_id = new_job_id(); filename = safe_name(syllabus.filename or "syllabus.docx")
        db.create_job(job_id, filename); folder = job_dir(root, job_id, "inbox"); folder.mkdir(parents=True)
        path = folder / filename; path.write_bytes(await syllabus.read())
        background.add_task(normalize, job_id, path)
        return RedirectResponse(f"/cblm/jobs/{job_id}", 303)

    @router.get("/jobs/{job_id}", response_class=HTMLResponse)
    def job(request: Request, job_id: str):
        row=require(job_id)
        if row["status"]=="review": return RedirectResponse(f"/cblm/jobs/{job_id}/plan",303)
        if row["status"] in {"approved","generating","paused","failed"}: return RedirectResponse(f"/cblm/jobs/{job_id}/progress",303)
        if row["status"] in {"success","finished"}: return RedirectResponse(f"/cblm/jobs/{job_id}/result",303)
        return web.TemplateResponse(request,"waiting.html",{"job":row})

    @router.get("/jobs/{job_id}/plan", response_class=HTMLResponse)
    def plan_page(request: Request, job_id: str):
        row=require(job_id); plan=CBLMPlan.model_validate_json(row["plan_json"])
        return web.TemplateResponse(request,"plan.html",{"job":row,"plan":plan})

    @router.post("/jobs/{job_id}/approve")
    async def approve(request: Request, job_id: str):
        row=require(job_id); plan=CBLMPlan.model_validate_json(row["plan_json"]); form=await request.form()
        plan.course.sector=str(form.get("sector","")); plan.course.course_title=str(form.get("course_title","")); plan.course.course_code=str(form.get("course_code","")); plan.course.name=str(form.get("name","")); plan.course.font_family=str(form.get("font_family","Bookman Old Style")); plan.course.font_size=float(form.get("font_size",12))
        for lo in plan.learning_outcomes:
            p=f"lo_{lo.number}_"; lo.learning_outcome=str(form.get(p+"outcome",lo.learning_outcome)); lo.duration=float(form.get(p+"duration",lo.duration)); lo.location=str(form.get(p+"location","")); lo.laboratory=str(form.get(p+"laboratory","")); lo.training_materials=[x.strip() for x in str(form.get(p+"materials","")).splitlines() if x.strip()]
            for topic in lo.topics: topic.title=str(form.get(f"{p}topic_{topic.number}",topic.title))
        if row["status"] != "approved": transition(root,job_id,row["status"],"approved")
        db.update_job(job_id,status="approved",progress=0,message="Approved; ready for automatic generation",plan_json=plan.model_dump_json(),control_json=json.dumps({"concurrency":int(form.get("concurrency",1))}))
        return RedirectResponse(f"/cblm/jobs/{job_id}/progress",303)

    @router.post("/jobs/{job_id}/generate")
    async def generate(job_id: str):
        row=require(job_id)
        if row["status"] not in {"approved","paused","failed"}: raise HTTPException(409,"This job cannot generate now")
        db.set_control(job_id,cancel=False); service.start(job_id)
        return RedirectResponse(f"/cblm/jobs/{job_id}/progress",303)

    @router.get("/jobs/{job_id}/progress", response_class=HTMLResponse)
    def progress(request: Request,job_id:str): return web.TemplateResponse(request,"progress.html",{"job":require(job_id),"stages":db.stages(job_id)})

    @router.get("/jobs/{job_id}/status")
    def status(job_id:str): return JSONResponse({"job":require(job_id),"stages":db.stages(job_id)})

    def log_files(job_id: str):
        entries = []
        for bucket in ("Success", "Failed"):
            for path in (root / "JSON Dump" / bucket).glob(f"{job_id}-*.json"):
                name = path.name
                kind = "request" if "-request-" in name else "response" if "-response-" in name else "rejected" if "-failed-" in name else "diagnostic"
                stat = path.stat()
                entries.append({"name": name, "bucket": bucket.lower(), "kind": kind, "size": stat.st_size,
                                "updated_at": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat()})
        return sorted(entries, key=lambda item: item["updated_at"], reverse=True)[:200]

    @router.get("/jobs/{job_id}/llm-logs")
    def llm_logs(job_id: str):
        row = require(job_id)
        return {"job": {key: row.get(key) for key in ("status", "progress", "message", "error")},
                "stages": db.stages(job_id), "live": service.live_for(job_id), "entries": log_files(job_id)}

    @router.get("/jobs/{job_id}/llm-logs/{bucket}/{filename}")
    def llm_log(job_id: str, bucket: str, filename: str):
        require(job_id)
        if bucket not in {"success", "failed"} or Path(filename).name != filename or not filename.startswith(job_id + "-") or not filename.endswith(".json"):
            raise HTTPException(400, "Invalid log file")
        path = root / "JSON Dump" / bucket.title() / filename
        if not path.exists(): raise HTTPException(404, "Log entry not found")
        return JSONResponse(json.loads(path.read_text(encoding="utf-8")))

    @router.post("/jobs/{job_id}/stop")
    def stop(job_id:str): db.set_control(job_id,cancel=True); return RedirectResponse(f"/cblm/jobs/{job_id}/progress",303)

    @router.post("/jobs/{job_id}/back")
    def back(job_id:str):
        row=require(job_id); db.set_control(job_id,cancel=True); transition(root,job_id,row["status"],"review"); db.update_job(job_id,status="review",message="Returned to planning"); return RedirectResponse(f"/cblm/jobs/{job_id}/plan",303)

    @router.post("/jobs/{job_id}/delete")
    def delete(job_id:str):
        row=require(job_id); folder=job_dir(root,job_id,row["status"])
        if folder.exists(): shutil.rmtree(folder)
        db.delete_job(job_id); return RedirectResponse("/cblm",303)

    @router.get("/jobs/{job_id}/result", response_class=HTMLResponse)
    def result(request:Request,job_id:str):
        row=require(job_id); folder=job_dir(root,job_id,row["status"]); files=list((folder/"CBLMs").glob("*.docx")) if (folder/"CBLMs").exists() else []
        return web.TemplateResponse(request,"result.html",{"job":row,"files":files})

    @router.get("/jobs/{job_id}/download/{name}")
    def download(job_id:str,name:str):
        row=require(job_id); folder=job_dir(root,job_id,row["status"]); path=(folder/"cblm-course.zip") if name=="zip" else (folder/"CBLMs"/Path(name).name)
        if not path.exists(): raise HTTPException(404,"File not found")
        return FileResponse(path,filename=path.name)
    return router
