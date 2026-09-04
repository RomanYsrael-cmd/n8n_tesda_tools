from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import AuthService
from .billing import verify_paymongo_signature
from .config import load_config
from .database import SaaSDatabase
from .storage import ObjectStore

ROOT = Path(__file__).resolve().parent


def install_saas(app: FastAPI) -> None:
    cfg = load_config(); db = SaaSDatabase(cfg.database_url); db.migrate()
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["tools.romanlms.com", "localhost", "127.0.0.1"])

    @app.middleware("http")
    async def production_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://www.gstatic.com; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' https://*.googleapis.com https://identitytoolkit.googleapis.com; "
            "img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        return response
    auth_service, store = AuthService(cfg, db), ObjectStore(cfg)
    router, templates = APIRouter(), Jinja2Templates(directory=ROOT / "templates")
    app.mount("/saas-static", StaticFiles(directory=ROOT / "static"), name="saas-static")

    def context(request: Request, **extra):
        return {"request":request, "user":auth_service.current(request, required=False),
                "firebase":{"apiKey":cfg.firebase_web_api_key,"projectId":cfg.firebase_project_id}, **extra}

    @router.get("/login", response_class=HTMLResponse)
    def login(request: Request):
        if auth_service.current(request, required=False): return RedirectResponse("/app", 303)
        return templates.TemplateResponse(request, "login.html", context(request))

    @router.post("/auth/session")
    async def session(request: Request):
        body = await request.json(); cookie = auth_service.exchange(body.get("idToken", ""))
        response = JSONResponse({"ok":True}); response.set_cookie(auth_service.COOKIE, cookie, max_age=604800,
            httponly=True, secure=True, samesite="lax", path="/")
        return response

    @router.post("/auth/logout")
    def logout():
        response = RedirectResponse("/login", 303); response.delete_cookie(auth_service.COOKIE, path="/"); return response

    @router.get("/app", response_class=HTMLResponse)
    def dashboard(request: Request):
        user = auth_service.current(request, required=False)
        if not user: return RedirectResponse("/login", 303)
        return templates.TemplateResponse(request, "dashboard.html", context(request, user=user, jobs=db.jobs(user.id)))

    @router.post("/app/jobs")
    async def upload(request: Request, tool: str=Form(...), syllabus: UploadFile=File(...)):
        user = auth_service.current(request)
        if tool not in {"module","cblm"}: raise HTTPException(400, "Choose a supported builder")
        filename = re.sub(r"[^A-Za-z0-9._ -]", "_", syllabus.filename or "syllabus.docx").strip()
        data = await syllabus.read()
        if not filename.lower().endswith(".docx") or not data.startswith(b"PK"):
            raise HTTPException(400, "Upload a valid DOCX syllabus")
        if len(data) > 25 * 1024 * 1024: raise HTTPException(413, "Syllabus must be 25 MB or smaller")
        job_id = str(uuid.uuid4()); key = f"users/{user.id}/jobs/{job_id}/input/{filename}"
        await asyncio.to_thread(store.put_bytes, key, data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        db.create_job(job_id, user.id, tool, filename, key)
        return RedirectResponse(f"/app/jobs/{job_id}", 303)

    @router.get("/app/jobs/{job_id}", response_class=HTMLResponse)
    def job_page(request: Request, job_id: str):
        user = auth_service.current(request); job = db.job(job_id, user.id)
        if not job: raise HTTPException(404, "Job not found")
        if job["status"] == "review": return RedirectResponse(f"/app/jobs/{job_id}/plan", 303)
        return templates.TemplateResponse(request, "job.html", context(request, user=user, job=job))

    @router.get("/app/jobs/{job_id}/plan", response_class=HTMLResponse)
    def plan_page(request: Request, job_id: str, saved: int=0):
        user=auth_service.current(request); job=db.job(job_id,user.id)
        if not job: raise HTTPException(404,"Job not found")
        if job["status"] != "review": return RedirectResponse(f"/app/jobs/{job_id}",303)
        plan=(job.get("payload") or {}).get("normalized")
        if not plan: raise HTTPException(409,"The extracted plan is not ready yet")
        template="plan_module.html" if job["tool"] == "module" else "plan_cblm.html"
        return templates.TemplateResponse(request,template,context(request,user=user,job=job,plan=plan,saved=bool(saved)))

    async def reviewed_plan(request: Request, job: dict) -> dict:
        form=await request.form(); original=(job.get("payload") or {}).get("normalized") or {}
        if job["tool"] == "module":
            from app.schemas import NormalizedSyllabus
            plan=NormalizedSyllabus.model_validate(original); c=plan.course
            c.code=str(form.get("course_code","")); c.title=str(form.get("course_title","")); c.author=str(form.get("author","")); c.trainer=str(form.get("trainer","")); c.description=str(form.get("description","")); c.font_family=str(form.get("font_family","Times New Roman")); c.font_size=float(form.get("font_size",12))
            lesson=0
            for i,week in enumerate(plan.weeks):
                p=f"week_{i}_"; week.generate=form.get(p+"generate") == "on"; week.proposed_title=str(form.get(p+"title","")).strip(); week.learning_outcome=str(form.get(p+"outcome","")).strip(); week.topic_scope=str(form.get(p+"scope","")).strip(); week.session=str(form.get(p+"session","")).strip(); week.type=str(form.get(p+"type",week.type)); week.skipped_reason=str(form.get(p+"reason","")).strip()
                if week.generate: lesson+=1; week.lesson_number=lesson
                else: week.lesson_number=None
            return NormalizedSyllabus.model_validate(plan.model_dump()).model_dump(mode="json")
        from cblm_app.schemas import CBLMPlan
        plan=CBLMPlan.model_validate(original); c=plan.course
        c.sector=str(form.get("sector","")); c.course_title=str(form.get("course_title","")); c.course_code=str(form.get("course_code","")); c.name=str(form.get("name","")); c.font_family=str(form.get("font_family","Bookman Old Style")); c.font_size=float(form.get("font_size",12))
        for li,lo in enumerate(plan.learning_outcomes):
            p=f"lo_{li}_"; lo.learning_outcome=str(form.get(p+"outcome","")).strip(); lo.duration=float(form.get(p+"duration",lo.duration)); lo.location=str(form.get(p+"location","")).strip(); lo.laboratory=str(form.get(p+"laboratory","")).strip(); lo.training_materials=[x.strip() for x in str(form.get(p+"materials","")).splitlines() if x.strip()]
            for ti,topic in enumerate(lo.topics): topic.title=str(form.get(f"{p}topic_{ti}","")).strip(); topic.include=form.get(f"{p}include_{ti}") == "on"
        return CBLMPlan.model_validate(plan.model_dump()).model_dump(mode="json")

    @router.post("/app/jobs/{job_id}/plan/save")
    async def save_plan(request: Request, job_id: str):
        user=auth_service.current(request); job=db.job(job_id,user.id)
        if not job: raise HTTPException(404,"Job not found")
        try: normalized=await reviewed_plan(request,job)
        except Exception as exc: raise HTTPException(422,f"Please correct the plan: {exc}") from exc
        if not db.save_plan(job_id,user.id,{"normalized":normalized}): raise HTTPException(409,"This plan can no longer be edited")
        return RedirectResponse(f"/app/jobs/{job_id}/plan?saved=1",303)

    @router.post("/app/jobs/{job_id}/plan/approve")
    async def approve_plan(request: Request, job_id: str):
        user=auth_service.current(request); job=db.job(job_id,user.id)
        if not job: raise HTTPException(404,"Job not found")
        try: normalized=await reviewed_plan(request,job)
        except Exception as exc: raise HTTPException(422,f"Please correct the plan: {exc}") from exc
        if not db.approve(job_id,user.id,{"normalized":normalized}): raise HTTPException(409,"This plan cannot be approved now")
        return RedirectResponse(f"/app/jobs/{job_id}",303)

    @router.get("/app/jobs/{job_id}/status")
    def job_status(request: Request, job_id: str):
        user = auth_service.current(request); job = db.job(job_id, user.id)
        if not job: raise HTTPException(404, "Job not found")
        return {key:job[key] for key in ("status","stage","progress","message","error")}

    @router.get("/app/jobs/{job_id}/events")
    async def events(request: Request, job_id: str):
        user = auth_service.current(request)
        if not db.job(job_id, user.id): raise HTTPException(404, "Job not found")
        async def stream():
            cursor = int(request.headers.get("last-event-id", "0") or 0)
            while not await request.is_disconnected():
                for event in db.events(job_id, cursor):
                    cursor = event["id"]
                    payload = {k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in event.items()}
                    yield f"id: {cursor}\nevent: progress\ndata: {json.dumps(payload, default=str)}\n\n"
                yield ": keepalive\n\n"; await asyncio.sleep(2)
        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

    @router.get("/app/jobs/{job_id}/activity")
    def activity(request: Request, job_id: str, after: int=0):
        user=auth_service.current(request)
        if not db.job(job_id,user.id): raise HTTPException(404,"Job not found")
        rows=db.events(job_id,after)
        return {"events":[{k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in row.items()} for row in rows], "next":rows[-1]["id"] if rows else after}

    @router.post("/app/jobs/{job_id}/approve")
    async def approve(request: Request, job_id: str, normalized_json: str=Form(...)):
        user = auth_service.current(request); job = db.job(job_id, user.id)
        if not job: raise HTTPException(404, "Job not found")
        try:
            value = json.loads(normalized_json)
            if job["tool"] == "module":
                from app.schemas import NormalizedSyllabus
                normalized = NormalizedSyllabus.model_validate(value).model_dump(mode="json")
            else:
                from cblm_app.schemas import CBLMPlan
                normalized = CBLMPlan.model_validate(value).model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(422, f"The reviewed plan is invalid: {exc}") from exc
        if not db.approve(job_id, user.id, {"normalized":normalized}):
            raise HTTPException(409, "This plan cannot be approved in its current state")
        return RedirectResponse(f"/app/jobs/{job_id}", 303)

    @router.post("/app/jobs/{job_id}/cancel")
    def cancel(request: Request, job_id: str):
        user = auth_service.current(request)
        if not db.cancel(job_id, user.id): raise HTTPException(409, "This job can no longer be cancelled")
        return RedirectResponse(f"/app/jobs/{job_id}", 303)

    @router.post("/app/jobs/{job_id}/delete")
    def delete_job(request: Request, job_id: str):
        user=auth_service.current(request); job=db.job(job_id,user.id)
        if not job: raise HTTPException(404,"Job not found")
        db.cancel(job_id,user.id)
        if not db.delete_job(job_id,user.id): raise HTTPException(409,"This course could not be deleted")
        try: store.delete_prefix(f"users/{user.id}/jobs/{job_id}/")
        except Exception: pass
        return RedirectResponse("/app",303)

    @router.post("/app/jobs/{job_id}/resume")
    def resume(request: Request, job_id: str):
        user=auth_service.current(request)
        if not db.resume(job_id,user.id): raise HTTPException(409,"This course cannot resume from its current state")
        return RedirectResponse(f"/app/jobs/{job_id}",303)

    @router.post("/app/jobs/{job_id}/back-to-planning")
    def back_to_planning(request: Request, job_id: str):
        user=auth_service.current(request)
        if not db.return_to_plan(job_id,user.id): raise HTTPException(409,"This course cannot return to planning")
        return RedirectResponse(f"/app/jobs/{job_id}/plan",303)

    @router.get("/app/jobs/{job_id}/download")
    def download(request: Request, job_id: str):
        user = auth_service.current(request); job = db.job(job_id, user.id)
        if not job or not job.get("output_key"): raise HTTPException(404, "No downloadable result is available")
        return RedirectResponse(store.signed_download(job["output_key"]), 303)

    @router.post("/webhooks/paymongo")
    async def paymongo(request: Request):
        body = await request.body(); payload = verify_paymongo_signature(body, request.headers.get("paymongo-signature", ""), cfg.paymongo_webhook_secret)
        event = payload.get("data", {}); external_id = event.get("id")
        if not external_id: raise HTTPException(400, "Webhook event ID is missing")
        with db.connection() as conn:
            conn.execute("INSERT INTO saas_webhook_events(provider,external_id,payload) VALUES('paymongo',%s,%s) ON CONFLICT DO NOTHING", (external_id, json.dumps(payload)))
        return {"received":True}

    @router.get("/health/saas")
    def health():
        with db.connection() as conn: conn.execute("SELECT 1")
        return {"status":"ok","mode":"saas","database":"ok","public_url":cfg.public_url}

    app.include_router(router)
