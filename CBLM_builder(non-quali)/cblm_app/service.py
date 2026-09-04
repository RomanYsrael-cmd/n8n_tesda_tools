from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.validation import render_verify

from .documents import audit_docx, build_cblm, package_outputs
from .parsers import clean_response, parse_self_check, parse_task_sheet
from .prompts import PromptCatalog
from .schemas import CBLMPlan
from .storage import dump, job_dir, transition


class CBLMGenerationService:
    def __init__(self, root: Path, templates: Path, prompts: Path, db, provider_factory):
        self.root, self.templates, self.db, self.provider_factory = root, templates, db, provider_factory
        self.catalog = PromptCatalog.load(prompts)
        self.tasks: dict[str, asyncio.Task] = {}
        self.live_activity: dict[str, dict[str, dict]] = {}

    def live_for(self, job_id: str):
        return list(self.live_activity.get(job_id, {}).values())

    def _latest_payload(self, job_id: str, lo: int, topic: int, stage: str, failed: bool = False):
        bucket = self.root / "JSON Dump" / ("Failed" if failed else "Success")
        marker = "failed" if failed else "response"
        files = sorted(bucket.glob(f"{job_id}-lo{lo}-topic{topic}-{stage}-{marker}-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            return None
        return json.loads(files[0].read_text(encoding="utf-8"))

    def _restore_plan(self, job_id: str, plan: CBLMPlan):
        """Rebuild checkpoints from key-free JSON logs after a restart/failure."""
        for lo in plan.learning_outcomes:
            for stage, field in (("module_title", "module_title"), ("module_descriptor", "module_descriptor")):
                if not getattr(lo, field):
                    payload = self._latest_payload(job_id, lo.number, 0, stage)
                    if payload and payload.get("response"):
                        setattr(lo, field, clean_response(payload["response"]))
            for topic in lo.topics:
                for stage, field in (("lesson_objectives", "learning_objectives"), ("keyfacts_content", "keyfacts_content")):
                    if not getattr(topic, field):
                        payload = self._latest_payload(job_id, lo.number, topic.number, stage)
                        if payload and payload.get("response"):
                            setattr(topic, field, clean_response(payload["response"]))
                if not (topic.quiz and topic.answer_key):
                    payload = self._latest_payload(job_id, lo.number, topic.number, "self_check")
                    if payload and payload.get("response"):
                        parsed = parse_self_check(payload["response"])
                        topic.quiz_instructions, topic.quiz, topic.answer_key = parsed.quiz_instructions, parsed.quiz, parsed.answer_key
                if not (topic.activity_title and topic.activity_criteria):
                    payload = self._latest_payload(job_id, lo.number, topic.number, "task_sheet")
                    raw = payload.get("response", "") if payload else ""
                    if not raw:
                        payload = self._latest_payload(job_id, lo.number, topic.number, "task_sheet", failed=True)
                        raw = payload.get("rejected_text", "") if payload else ""
                    if raw:
                        try:
                            task = parse_task_sheet(raw)
                            topic.activity_title, topic.activity_objectives = task.activity_title, task.activity_objectives
                            topic.activity_supplies, topic.activity_equipment = task.activity_supplies, task.activity_equipment
                            topic.activity_steps, topic.activity_method, topic.activity_criteria = task.activity_steps, task.activity_method, task.activity_criteria
                            self.db.upsert_stage(job_id, lo.number, topic.number, "task_sheet", "success", "Recovered and normalized by Python")
                        except ValueError:
                            pass

    def start(self, job_id: str):
        task = self.tasks.get(job_id)
        if not task or task.done():
            self.tasks[job_id] = asyncio.create_task(self.run(job_id))

    async def _call(self, job_id, lo, topic, stage, prompt, parser=None):
        provider = self.provider_factory()
        for attempt in range(1, 4):
            raw = ""
            self.db.upsert_stage(job_id, lo, topic, stage, "running", f"Attempt {attempt}", True)
            dump(self.root, True, f"{job_id}-lo{lo}-topic{topic}-{stage}-request-{attempt}", {
                "prompt": prompt, "model": provider.model, "base_url": provider.base_url,
                "response_format": "text",
            })
            try:
                live_key = f"lo-{lo}-topic-{topic}-{stage}-{attempt}"
                live = {"id": live_key, "lo": lo, "topic": topic, "stage": stage,
                        "attempt": attempt, "status": "receiving", "content": ""}
                job_live = self.live_activity.setdefault(job_id, {})
                job_live[live_key] = live

                def receive_token(token: str):
                    live["content"] += token

                raw = await provider.complete_text(prompt, max_attempts=1, on_token=receive_token)
                live["status"] = "validating"
                dump(self.root, True, f"{job_id}-lo{lo}-topic{topic}-{stage}-response-{attempt}", {"response": raw})
                value = parser(raw) if parser else clean_response(raw)
                if not value:
                    raise ValueError("The provider returned empty content")
                self.db.upsert_stage(job_id, lo, topic, stage, "success", "Complete")
                job_live.pop(live_key, None)
                return value
            except Exception as exc:
                if 'live' in locals():
                    live["status"] = "rejected"
                    job_live.pop(live_key, None)
                dump(self.root, False, f"{job_id}-lo{lo}-topic{topic}-{stage}-failed-{attempt}", {"errors": [str(exc)], "rejected_text": raw, "prompt": prompt})
                self.db.upsert_stage(job_id, lo, topic, stage, "retrying" if attempt < 3 else "failed", str(exc))
                if attempt == 3:
                    raise
        raise RuntimeError("unreachable")

    async def run(self, job_id: str):
        row = self.db.get_job(job_id)
        if not row:
            return
        try:
            old = row["status"]
            if old != "generating":
                transition(self.root, job_id, old, "generating")
            self.db.update_job(job_id, status="generating", progress=1, message="Generating CBLMs", error=None)
            plan = CBLMPlan.model_validate_json(row["plan_json"])
            self._restore_plan(job_id, plan)
            self.db.update_job(job_id, plan_json=plan.model_dump_json())
            total_topics = sum(len(lo.topics) for lo in plan.learning_outcomes)
            completed = 0
            for lo in plan.learning_outcomes:
                control = json.loads((self.db.get_job(job_id) or {}).get("control_json") or "{}")
                if control.get("cancel"):
                    self.db.update_job(job_id, status="paused", message="Stopped by user")
                    return
                base = {"learning_outcome": lo.learning_outcome, "course_title": plan.course.course_title}
                title_prompt = self.catalog.render("module_title", base)
                topic_jobs = []
                for topic in lo.topics:
                    vals = self._values(plan, lo, topic)
                    topic_jobs.append(asyncio.sleep(0, result=topic.learning_objectives) if topic.learning_objectives else self._call(job_id, lo.number, topic.number, "lesson_objectives", self.catalog.render("lesson_objectives", vals)))
                title_job = asyncio.sleep(0, result=lo.module_title) if lo.module_title else self._call(job_id, lo.number, 0, "module_title", title_prompt)
                title_result, objectives = await asyncio.gather(title_job, asyncio.gather(*topic_jobs))
                lo.module_title = title_result
                for topic, value in zip(lo.topics, objectives): topic.learning_objectives = value
                desc_prompt = self.catalog.render("module_descriptor", {**base, "module_title": lo.module_title})
                key_jobs = [asyncio.sleep(0, result=t.keyfacts_content) if t.keyfacts_content else self._call(job_id, lo.number, t.number, "keyfacts_content", self.catalog.render("keyfacts_content", self._values(plan, lo, t))) for t in lo.topics]
                desc_job = asyncio.sleep(0, result=lo.module_descriptor) if lo.module_descriptor else self._call(job_id, lo.number, 0, "module_descriptor", desc_prompt)
                lo.module_descriptor, keyfacts = await asyncio.gather(desc_job, asyncio.gather(*key_jobs))
                for topic, value in zip(lo.topics, keyfacts): topic.keyfacts_content = value
                limit = max(1, min(4, int(json.loads((self.db.get_job(job_id) or {}).get("control_json") or "{}").get("concurrency", 1))))
                semaphore = asyncio.Semaphore(limit)
                async def finish_topic(topic):
                    async with semaphore:
                        values = self._values(plan, lo, topic)
                        quiz_prompt = self.catalog.render("self_check", values)
                        task_prompt = self.catalog.render("task_sheet", values)
                        if not (topic.quiz and topic.answer_key):
                            quiz = await self._call(job_id, lo.number, topic.number, "self_check", quiz_prompt, parse_self_check)
                            topic.quiz_instructions, topic.quiz, topic.answer_key = quiz.quiz_instructions, quiz.quiz, quiz.answer_key
                        if not (topic.activity_title and topic.activity_criteria):
                            task = await self._call(job_id, lo.number, topic.number, "task_sheet", task_prompt, parse_task_sheet)
                            topic.activity_title, topic.activity_objectives = task.activity_title, task.activity_objectives
                            topic.activity_supplies, topic.activity_equipment = task.activity_supplies, task.activity_equipment
                            topic.activity_steps, topic.activity_method, topic.activity_criteria = task.activity_steps, task.activity_method, task.activity_criteria
                await asyncio.gather(*(finish_topic(t) for t in lo.topics))
                self.db.update_job(job_id, plan_json=plan.model_dump_json())
                completed += len(lo.topics)
                self.db.update_job(job_id, plan_json=plan.model_dump_json(), progress=int(completed / total_topics * 80), message=f"Generated learning outcome {lo.number}")
            base_dir = job_dir(self.root, job_id, "generating")
            modules = base_dir / "CBLMs"
            reports = []
            for lo in plan.learning_outcomes:
                self.db.update_job(job_id, message=f"Assembling CBLM for learning outcome {lo.number}")
                path = await asyncio.to_thread(build_cblm, self.templates, modules, plan, lo)
                audit = audit_docx(path)
                render = await asyncio.to_thread(render_verify, path, base_dir / "render" / f"lo-{lo.number}")
                reports.append({"learning_outcome": lo.number, "file": path.name, "audit": audit, "render": render})
                if not audit["valid"] or not render.get("valid"):
                    raise ValueError(f"DOCX validation failed for learning outcome {lo.number}")
            (base_dir / "cblm-plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            (base_dir / "validation-report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
            self.db.update_job(job_id, message="Validating and packaging CBLM documents")
            package_outputs(base_dir)
            transition(self.root, job_id, "generating", "success")
            self.db.update_job(job_id, status="success", progress=100, message="CBLMs are ready", error=None, plan_json=plan.model_dump_json())
        except Exception as exc:
            self.db.update_job(job_id, status="failed", message="Generation stopped", error=str(exc))

    @staticmethod
    def _values(plan, lo, topic):
        return {"course": plan.course.course_title, "course_title": plan.course.course_title, "learning_outcome": lo.learning_outcome,
                "learning_objectives": topic.learning_objectives, "lesson_objectives": topic.learning_objectives,
                "source_material": topic.source_material or topic.resources, "topic": topic.title, "syllabus_topic": topic.title,
                "keyfacts_content": topic.keyfacts_content, "question_count": 10, "module_title": lo.module_title}
