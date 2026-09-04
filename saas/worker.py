from __future__ import annotations

import json
import asyncio
import os
import shutil
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from app.extraction import extract_syllabus
from app.config import Settings
from app.database import Database
from app.providers import OpenAICompatibleProvider
from app.schemas import JobStatus, NormalizedSyllabus
from app.services import GenerationService
from app.storage import ensure_layout, job_dir

from .config import load_config
from .database import SaaSDatabase
from .email import send_completed
from .storage import ObjectStore

if "/cblm" not in sys.path:
    sys.path.insert(0, "/cblm")


async def run_with_live_sync(coro, db: SaaSDatabase, local_db, job_id: str, runtime: Path, tool: str) -> None:
    """Run a local engine while copying its safe progress and JSON logs to SaaS."""
    task = asyncio.create_task(coro); stage_state: dict[str, tuple] = {}; seen_logs: set[str] = set()
    while not task.done():
        local_job = local_db.get_job(job_id) or {}; stages = local_db.stages(job_id)
        local_message = local_job.get("message") or "Generating documents"
        # Surface the long, non-LLM part of a run instead of leaving the UI at
        # “generation” while DOCX files are assembled, rendered, and packaged.
        assembly_words = ("assembling", "validating", "packaging", "rendering")
        cloud_stage = "assembly" if any(word in local_message.lower() for word in assembly_words) else "generation"
        db.update(job_id, stage=cloud_stage, progress=max(25, int(local_job.get("progress") or 0)), message=local_message)
        cloud_job = db.job(job_id)
        if not cloud_job or cloud_job.get("cancel_requested"): local_db.set_control(job_id, cancel=True)
        for stage in stages:
            key = ":".join(str(stage.get(k, 0)) for k in (("lesson_number","lo_number")[tool=="cblm"], ("actual_week","topic_number")[tool=="cblm"], "stage"))
            value = (stage.get("status"), stage.get("attempts"), stage.get("message"))
            if stage_state.get(key) != value:
                stage_state[key] = value; db.event(job_id, "stage", stage.get("message") or stage.get("stage", "Stage updated"), detail={"kind":"stage","tool":tool, **stage})
        for folder in (runtime / "JSON Dump" / "Success", runtime / "JSON Dump" / "Failed"):
            if not folder.exists(): continue
            for path in folder.glob(f"{job_id}*.json"):
                marker=str(path)
                if marker in seen_logs: continue
                seen_logs.add(marker)
                try: content=path.read_text(encoding="utf-8")[:250000]
                except Exception: continue
                label="response" if "response" in path.name else "request" if "request" in path.name else "diagnostic"
                db.event(job_id, "llm", f"LLM {label}: {path.name}", detail={"kind":"llm","label":label,"filename":path.name,"content":content})
        await asyncio.sleep(1)
    await task


def process(db: SaaSDatabase, store: ObjectStore, cfg, job: dict) -> None:
    job_id, user_id = str(job["id"]), job["user_id"]
    work = Path(tempfile.mkdtemp(prefix=f"tesda-{job_id[:8]}-"))
    try:
        source = work / job["filename"]
        store.download(job["input_key"], source)
        if db.job(job_id)["cancel_requested"]:
            db.update(job_id, status="cancelled", stage="cancelled", message="Cancelled", finished_at=datetime.now(UTC)); return
        if job["stage"] == "generation":
            generate(db, store, cfg, job, source, work)
            return
        if job["tool"] == "cblm":
            from cblm_app.extraction import extract_cblm_plan
            plan = extract_cblm_plan(source)
        else:
            plan = extract_syllabus(source)
        plan_path = work / "normalized-syllabus.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        output_key = f"users/{user_id}/jobs/{job_id}/normalized-syllabus.json"
        store.upload(output_key, plan_path, "application/json")
        db.update(job_id, status="review", stage="planning", progress=25,
                  message="Syllabus normalized and ready for review", output_key=output_key,
                  payload={"normalized": plan.model_dump(mode="json")})
        db.event(job_id, "planning", "Normalization complete; awaiting your approval")
    except Exception as exc:
        failed_stage = "generation" if job.get("stage") == "generation" else "normalization"
        db.update(job_id, status="failed", stage=failed_stage, message="Generation failed" if failed_stage == "generation" else "Syllabus could not be normalized",
                  error=str(exc), finished_at=datetime.now(UTC))
        db.event(job_id, "normalization", str(exc), "error")
        recipient = db.user_email(user_id)
        if recipient:
            try: send_completed(cfg, recipient, job["filename"], f"{cfg.public_url}/app/jobs/{job_id}", False)
            except Exception as mail_error: db.event(job_id, "notification", f"Email notification failed: {mail_error}", "warning")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def generate(db: SaaSDatabase, store: ObjectStore, cfg, job: dict, source: Path, work: Path) -> None:
    if not cfg.llm_base_url or not cfg.llm_model:
        raise RuntimeError("The platform-managed LLM is not configured")
    job_id, user_id = str(job["id"]), job["user_id"]
    runtime = work / "runtime"; provider = lambda: OpenAICompatibleProvider(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
    if job["tool"] == "module":
        ensure_layout(runtime); local_db = Database(runtime / "module-builder.sqlite3"); local_db.migrate()
        local_db.create_job(job_id, job["filename"])
        plan = NormalizedSyllabus.model_validate(job["payload"]["normalized"])
        local_db.update_job(job_id, status=JobStatus.APPROVED, normalized_json=plan.model_dump_json(), control_json='{"post_call_concurrency":1}')
        folder = job_dir(runtime, job_id, JobStatus.APPROVED); folder.mkdir(parents=True); shutil.copy2(source, folder / source.name)
        settings = Settings(data_root=runtime, template=Path("/templates/Module Template.docx"), use_n8n=False).resolved()
        service = GenerationService(settings, local_db, provider)
        asyncio.run(run_with_live_sync(service.run_auto(job_id), db, local_db, job_id, runtime, "module"))
        result = local_db.get_job(job_id)
        if result["status"] != JobStatus.SUCCESS: raise RuntimeError(result.get("error") or "Module generation failed")
        result_dir = job_dir(runtime, job_id, JobStatus.SUCCESS)
    else:
        from cblm_app.database import CBLMDatabase
        from cblm_app.schemas import CBLMPlan
        from cblm_app.service import CBLMGenerationService
        from cblm_app.storage import ensure_layout as ensure_cblm, job_dir as cblm_dir
        ensure_cblm(runtime); local_db=CBLMDatabase(runtime / "cblm.sqlite3"); local_db.migrate(); local_db.create_job(job_id,job["filename"])
        plan=CBLMPlan.model_validate(job["payload"]["normalized"]); local_db.update_job(job_id,status="approved",plan_json=plan.model_dump_json(),control_json='{"concurrency":1}')
        folder=cblm_dir(runtime,job_id,"approved"); folder.mkdir(parents=True); shutil.copy2(source,folder/source.name)
        service=CBLMGenerationService(runtime,Path("/cblm/Templates"),Path("/cblm/Prompts.xlsx"),local_db,provider)
        asyncio.run(run_with_live_sync(service.run(job_id), db, local_db, job_id, runtime, "cblm")); result=local_db.get_job(job_id)
        if result["status"] != "success": raise RuntimeError(result.get("error") or "CBLM generation failed")
        result_dir=cblm_dir(runtime,job_id,"success")
    archives=list(result_dir.glob("*.zip"))
    if not archives: raise RuntimeError("Generation completed without a deliverable ZIP")
    output_key=f"users/{user_id}/jobs/{job_id}/output/{archives[0].name}"
    store.upload(output_key,archives[0],"application/zip")
    db.update(job_id,status="success",stage="complete",progress=100,message="Documents are ready",output_key=output_key,finished_at=datetime.now(UTC))
    db.event(job_id,"complete","Generation and document validation completed")
    recipient = db.user_email(user_id)
    if recipient:
        try: send_completed(cfg, recipient, job["filename"], f"{cfg.public_url}/app/jobs/{job_id}", True)
        except Exception as exc: db.event(job_id, "notification", f"Email notification failed: {exc}", "warning")


def run() -> None:
    cfg = load_config(); db = SaaSDatabase(cfg.database_url); db.migrate(); store = ObjectStore(cfg)
    while True:
        job = db.claim()
        if job: process(db, store, cfg, job)
        else: time.sleep(2)


if __name__ == "__main__":
    run()
