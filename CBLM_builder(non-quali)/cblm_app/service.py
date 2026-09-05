from __future__ import annotations

import asyncio
import json
import math
import time
from pathlib import Path

from app.validation import render_verify
from app.providers import ProviderCancelled

from .documents import audit_docx, build_cblm, package_outputs
from .parsers import clean_response, parse_self_check, parse_task_sheet
from .prompts import PromptCatalog
from .schemas import CBLMPlan
from .storage import dump, job_dir, transition


def _token_estimate(characters: int) -> int:
    """Conservative display estimate for providers that omit tokenizer usage."""
    return math.ceil(max(0, characters) / 4)


class CBLMGenerationService:
    def __init__(self, root: Path, templates: Path, prompts: Path, db, provider_factory):
        self.root, self.templates, self.db, self.provider_factory = root, templates, db, provider_factory
        self.catalog = PromptCatalog.load(prompts)
        self.tasks: dict[str, asyncio.Task] = {}
        self.live_activity: dict[str, dict[str, dict]] = {}
        self._live_started: dict[str, float] = {}
        self._active_providers: dict[str, dict[int, object]] = {}

    def live_for(self, job_id: str):
        # Keep elapsed time moving during quiet provider/thinking periods.
        now = time.monotonic()
        for item in self.live_activity.get(job_id, {}).values():
            started = self._live_started.get(f"{job_id}:{item.get('id')}")
            if started is None:
                continue
            elapsed = max(now - started, 0.001)
            output_tokens = _token_estimate(int(item.get("output_characters") or len(item.get("content") or "")))
            item["elapsed_seconds"] = round(elapsed, 2)
            item["tokens_per_second"] = round(output_tokens / elapsed, 2)
        return list(self.live_activity.get(job_id, {}).values())

    def _track_provider(self, job_id: str, provider) -> None:
        self._active_providers.setdefault(job_id, {})[id(provider)] = provider

    def _untrack_provider(self, job_id: str, provider) -> None:
        providers = self._active_providers.get(job_id)
        if not providers:
            return
        providers.pop(id(provider), None)
        if not providers:
            self._active_providers.pop(job_id, None)

    async def cancel_active_requests(self, job_id: str) -> list[dict]:
        providers = list((self._active_providers.get(job_id) or {}).values())
        if not providers:
            return []
        calls = [provider.cancel_active_requests() for provider in providers if getattr(provider, "cancel_active_requests", None)]
        batches = await asyncio.gather(*calls)
        return [result for batch in batches for result in batch]

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
                started = time.monotonic()
                live = {"id": live_key, "lo": lo, "topic": topic, "stage": stage,
                        "attempt": attempt, "status": "connecting", "content": "",
                        "prompt_characters": len(prompt),
                        "prompt_tokens_estimate": _token_estimate(len(prompt)),
                        "output_characters": 0, "output_tokens_estimate": 0,
                        "reasoning_characters": 0, "elapsed_seconds": 0.0,
                        "tokens_per_second": 0.0, "request_id": "", "usage": None}
                job_live = self.live_activity.setdefault(job_id, {})
                job_live[live_key] = live
                self._live_started[f"{job_id}:{live_key}"] = started

                def update_telemetry():
                    elapsed = max(time.monotonic() - started, 0.001)
                    output_characters = len(live["content"])
                    output_tokens = _token_estimate(output_characters)
                    live["elapsed_seconds"] = round(elapsed, 2)
                    live["output_characters"] = output_characters
                    live["output_tokens_estimate"] = output_tokens
                    live["tokens_per_second"] = round(output_tokens / elapsed, 2)

                def receive_token(token: str):
                    live["status"] = "receiving"
                    live["content"] += token
                    update_telemetry()

                def receive_progress(info: dict):
                    if info.get("qwen_request_id"):
                        live["request_id"] = info["qwen_request_id"]
                    if info.get("reasoning_characters") is not None:
                        live["reasoning_characters"] = int(info.get("reasoning_characters") or 0)
                    if info.get("usage"):
                        live["usage"] = dict(info["usage"])
                    update_telemetry()

                self._track_provider(job_id, provider)
                try:
                    raw = await provider.complete_text(prompt, max_attempts=1, on_token=receive_token,
                                                       on_progress=receive_progress)
                finally:
                    self._untrack_provider(job_id, provider)
                update_telemetry()
                live["status"] = "validating"
                dump(self.root, True, f"{job_id}-lo{lo}-topic{topic}-{stage}-response-{attempt}", {"response": raw, "telemetry": dict(live) | {"content": ""}})
                value = parser(raw) if parser else clean_response(raw)
                if not value:
                    raise ValueError("The provider returned empty content")
                self.db.upsert_stage(job_id, lo, topic, stage, "success", "Complete")
                job_live.pop(live_key, None)
                self._live_started.pop(f"{job_id}:{live_key}", None)
                return value
            except ProviderCancelled:
                if 'live' in locals():
                    live["status"] = "cancelled"
                    job_live.pop(live_key, None)
                    self._live_started.pop(f"{job_id}:{live_key}", None)
                raise
            except Exception as exc:
                if 'live' in locals():
                    live["status"] = "rejected"
                    job_live.pop(live_key, None)
                    self._live_started.pop(f"{job_id}:{live_key}", None)
                dump(self.root, False, f"{job_id}-lo{lo}-topic{topic}-{stage}-failed-{attempt}", {"errors": [str(exc)], "rejected_text": raw, "prompt": prompt, "telemetry": dict(live) | {"content": ""} if 'live' in locals() else {}})
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
                    values = self._values(plan, lo, topic)
                    quiz_prompt = self.catalog.render("self_check", values)
                    task_prompt = self.catalog.render("task_sheet", values)

                    # Both calls use the same completed Key Facts content and
                    # are independent of one another. Acquire the semaphore
                    # per request (rather than around the whole topic) so a
                    # Self Check and Task Sheet can run in parallel while the
                    # configured global concurrency limit is still respected.
                    async def generate_quiz():
                        async with semaphore:
                            return await self._call(job_id, lo.number, topic.number, "self_check", quiz_prompt, parse_self_check)

                    async def generate_task():
                        async with semaphore:
                            return await self._call(job_id, lo.number, topic.number, "task_sheet", task_prompt, parse_task_sheet)

                    calls = []
                    if not (topic.quiz and topic.answer_key):
                        calls.append(("quiz", generate_quiz()))
                    if not (topic.activity_title and topic.activity_criteria):
                        calls.append(("task", generate_task()))
                    results = await asyncio.gather(*(call for _, call in calls))
                    for (kind, _), value in zip(calls, results):
                        if kind == "quiz":
                            topic.quiz_instructions, topic.quiz, topic.answer_key = value.quiz_instructions, value.quiz, value.answer_key
                        else:
                            topic.activity_title, topic.activity_objectives = value.activity_title, value.activity_objectives
                            topic.activity_supplies, topic.activity_equipment = value.activity_supplies, value.activity_equipment
                            topic.activity_steps, topic.activity_method, topic.activity_criteria = value.activity_steps, value.activity_method, value.activity_criteria
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
        except ProviderCancelled:
            self.db.update_job(job_id, status="paused", message="Stopped by user; completed work was preserved", error=None)
        except Exception as exc:
            self.db.update_job(job_id, status="failed", message="Generation stopped", error=str(exc))

    @staticmethod
    def _values(plan, lo, topic):
        return {"course": plan.course.course_title, "course_title": plan.course.course_title, "learning_outcome": lo.learning_outcome,
                "learning_objectives": topic.learning_objectives, "lesson_objectives": topic.learning_objectives,
                "source_material": topic.source_material or topic.resources, "topic": topic.title, "syllabus_topic": topic.title,
                "keyfacts_content": topic.keyfacts_content, "question_count": 10, "module_title": lo.module_title}
