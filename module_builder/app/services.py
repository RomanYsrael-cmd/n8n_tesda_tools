from __future__ import annotations

import asyncio
import json
import traceback
from pathlib import Path

from pydantic import ValidationError

from .content_parsers import extract_marked_response, parse_aiken_quiz, parse_apply_markdown, parse_introduction, parse_preassessment, parse_presentation_markdown
from .config import Settings
from .database import Database
from .docx_engine import build_module, package_course
from .prompts import (automatic_apply_prompt, automatic_introduction_prompt, automatic_preassessment_prompt,
                      automatic_presentation_prompt, automatic_self_check_prompt, repair_prompt,
                      semantic_validation_prompt, text_repair_prompt)
from .providers import OpenAICompatibleProvider
from .schemas import ApplyContent, JobStatus, ModuleBundle, NormalizedSyllabus, PresentationContent, QuizContent, SemanticReview
from .storage import dump_json, job_dir, transition
from .validation import audit_docx, render_verify, report_json, validate_bundle, validate_bundle_against_plan


class GenerationService:
    def __init__(self, settings: Settings, db: Database, provider_factory, semantic_enabled=lambda: False):
        self.settings = settings
        self.db = db
        self.provider_factory = provider_factory
        self.semantic_enabled = semantic_enabled
        self.tasks: dict[str, asyncio.Task] = {}
        self.live_activity: dict[str, dict[str, dict]] = {}

    def live_for(self, job_id: str) -> list[dict]:
        return list(self.live_activity.get(job_id, {}).values())

    def start(self, job_id: str):
        current = self.tasks.get(job_id)
        if current and not current.done():
            return
        self.db.set_control(job_id, pause=False, cancel=False)
        self.tasks[job_id] = asyncio.create_task(self.run_auto(job_id))

    async def stop(self, job_id: str):
        task = self.tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.tasks.pop(job_id, None)
        self.live_activity.pop(job_id, None)

    async def _validated_call(self, job_id: str, lesson: int, week: int, stage: str, prompt: str, model_type):
        provider: OpenAICompatibleProvider = self.provider_factory()
        current_prompt = prompt
        for repair in range(3):
            self.db.upsert_stage(job_id, lesson, week, stage, "running", f"Request attempt {repair + 1}", increment=True)
            request_path = dump_json(self.settings.data_root, True, f"{job_id}-lesson-{lesson}-{stage}-request-{repair+1}", {"prompt": current_prompt, "model": provider.model, "base_url": provider.base_url})
            raw = await provider.complete_json(current_prompt)
            try:
                value = model_type.model_validate(raw)
                errors = []
                if model_type is QuizContent and len(value.questions) != self.settings.quiz_questions:
                    errors.append(f"questions: expected exactly {self.settings.quiz_questions}, received {len(value.questions)}")
                if errors:
                    dump_json(self.settings.data_root, False, f"{job_id}-lesson-{lesson}-{stage}-invalid-{repair+1}", {"errors": errors, "rejected": raw})
                    current_prompt = repair_prompt(errors, raw)
                    continue
                dump_json(self.settings.data_root, True, f"{job_id}-lesson-{lesson}-{stage}-response-{repair+1}", raw)
                self.db.upsert_stage(job_id, lesson, week, stage, "success", "Validated response accepted")
                return value
            except ValidationError as exc:
                errors = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
                dump_json(self.settings.data_root, False, f"{job_id}-lesson-{lesson}-{stage}-invalid-{repair+1}", {"errors": errors, "rejected": raw})
                current_prompt = repair_prompt(errors, raw)
        self.db.upsert_stage(job_id, lesson, week, stage, "failed", "Validation failed after two repair attempts")
        raise ValueError(f"{stage} failed validation after two repair attempts")

    async def _validated_text(self, job_id: str, lesson: int, week: int, stage: str, prompt: str, parser, format_name: str):
        provider: OpenAICompatibleProvider = self.provider_factory()
        current_prompt = prompt
        request_options = {
            "presentation": {"web_search": True, "enable_thinking": False},
            "quiz": {"web_search": False, "enable_thinking": False},
            "introduction": {"web_search": "auto", "enable_thinking": False},
            "pre_assessment": {"web_search": "auto", "enable_thinking": False},
            "practical_activity": {"web_search": "auto", "enable_thinking": False},
        }.get(stage, {})
        for repair in range(3):
            self.db.upsert_stage(job_id, lesson, week, stage, "running", f"Request attempt {repair + 1}", increment=True)
            dump_json(self.settings.data_root, True, f"{job_id}-lesson-{lesson}-{stage}-request-{repair+1}", {"prompt": current_prompt, "model": provider.model, "base_url": provider.base_url, "response_format": "text", "request_options": request_options})
            live_key = f"lesson-{lesson}-{stage}-{repair + 1}"
            live = {"id": live_key, "lesson": lesson, "week": week, "stage": stage,
                    "attempt": repair + 1, "status": "receiving", "content": ""}
            job_live = self.live_activity.setdefault(job_id, {})
            job_live[live_key] = live

            def receive_token(token: str):
                live["content"] += token

            try:
                raw = await provider.complete_text(current_prompt, on_token=receive_token, request_options=request_options)
                live["status"] = "validating"
            except Exception:
                live["status"] = "failed"
                raise
            try:
                extracted = extract_marked_response(raw)
                value = parser(extracted)
                dump_json(self.settings.data_root, True, f"{job_id}-lesson-{lesson}-{stage}-response-{repair+1}", {"raw_text": raw, "extracted_text": extracted})
                self.db.upsert_stage(job_id, lesson, week, stage, "success", "Parsed and validated response accepted")
                live["status"] = "accepted"
                job_live.pop(live_key, None)
                return value, extracted
            except (ValueError, ValidationError) as exc:
                errors = [str(exc)]
                if isinstance(exc, ValidationError):
                    errors = [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]
                dump_json(self.settings.data_root, False, f"{job_id}-lesson-{lesson}-{stage}-invalid-{repair+1}", {"errors": errors, "rejected_text": raw})
                live["status"] = "rejected"
                job_live.pop(live_key, None)
                # A malformed quiz is more reliably replaced than patched,
                # especially with smaller local models. Each quiz retry uses
                # the complete original generation prompt and receives no
                # rejected response or correction instructions.
                current_prompt = prompt if stage == "quiz" else text_repair_prompt(format_name, errors, raw)
        failure_message = "Validation failed after three fresh generation attempts" if stage == "quiz" else "Validation failed after two repair attempts"
        self.db.upsert_stage(job_id, lesson, week, stage, "failed", failure_message)
        raise ValueError(f"{stage} {failure_message.casefold()}")

    async def run_auto(self, job_id: str):
        row = self.db.get_job(job_id)
        try:
            plan = NormalizedSyllabus.model_validate_json(row["normalized_json"])
            self.db.update_job(job_id, status=JobStatus.GENERATING, mode="automatic", message="Generating modules")
            base = job_dir(self.settings.data_root, job_id, JobStatus.GENERATING)
            modules_dir = base / "modules"
            generated = []
            weeks = [w for w in plan.weeks if w.generate]
            completed = {(s["lesson_number"], s["stage"]) for s in self.db.stages(job_id) if s["status"] == "success"}
            for index, week in enumerate(weeks):
                control = json.loads(self.db.get_job(job_id)["control_json"] or "{}")
                if control.get("cancel"):
                    self.db.update_job(job_id, status=JobStatus.CANCELLED, message="Remaining modules cancelled")
                    return
                if control.get("pause"):
                    self.db.update_job(job_id, status=JobStatus.PAUSED, message="Paused after current module")
                    return
                lesson = week.lesson_number or index + 1
                existing = list(modules_dir.glob(f"Week {week.actual_week:02d} - Lesson {lesson:02d} - *.docx"))
                if (lesson, "validation") in completed and existing:
                    generated.append({"lesson": lesson, "week": week.actual_week, "file": existing[0].name, "resumed": True})
                    self.db.update_job(job_id, progress=int((index + 1) / len(weeks) * 100), message=f"Kept completed Lesson {lesson}")
                    continue
                draft, presentation_markdown = await self._validated_text(job_id, lesson, week.actual_week, "presentation", automatic_presentation_prompt(plan, week), parse_presentation_markdown, "Markdown presentation")
                stage_calls = [
                    ("introduction", automatic_introduction_prompt(presentation_markdown), parse_introduction, "plain-text introduction"),
                    ("pre_assessment", automatic_preassessment_prompt(presentation_markdown), parse_preassessment, "Markdown pre-assessment"),
                    ("quiz", automatic_self_check_prompt(presentation_markdown), parse_aiken_quiz, "Aiken-style Self Check"),
                    ("practical_activity", automatic_apply_prompt(presentation_markdown), parse_apply_markdown, "Markdown Let's Apply activity"),
                ]
                control = json.loads(self.db.get_job(job_id)["control_json"] or "{}")
                concurrency = max(1, min(4, int(control.get("post_call_concurrency", 1))))
                semaphore = asyncio.Semaphore(concurrency)

                async def run_stage(stage, prompt, parser, format_name):
                    async with semaphore:
                        return await self._validated_text(job_id, lesson, week.actual_week, stage, prompt, parser, format_name)

                results = await asyncio.gather(*[
                    run_stage(stage, prompt, parser, format_name)
                    for stage, prompt, parser, format_name in stage_calls
                ])
                (introduction, _), (pre_assessment, _), (quiz, _), (practical, _) = results
                objectives = draft.objectives or ([week.learning_outcome] if week.learning_outcome.strip() else [f"Study {week.proposed_title}"])
                presentation = PresentationContent.model_validate({"lesson_title": week.proposed_title, "information_sheet_title": f"Key Facts {lesson}.1 – {week.proposed_title}", "measurable_objectives": objectives, "pre_assessment": pre_assessment, "introduction": introduction, "presentation": draft.blocks, "references": draft.references}, context={"automatic": True})
                bundle = ModuleBundle.model_validate(
                    {
                        "actual_week": week.actual_week,
                        "lesson_number": lesson,
                        "approved_scope": week.topic_scope,
                        "presentation": presentation.model_dump(),
                        "quiz": quiz.model_dump(),
                        "practical_activity": practical.model_dump(),
                    },
                    context={"automatic": True},
                )
                validated, errors = validate_bundle(bundle.model_dump(), self.settings.quiz_questions, automatic=True)
                errors += validate_bundle_against_plan(bundle, plan, automatic=True)
                if errors:
                    raise ValueError("; ".join(errors))
                if self.semantic_enabled():
                    review = await self._validated_call(job_id, lesson, week.actual_week, "semantic_validation", semantic_validation_prompt(plan, bundle), SemanticReview)
                    if not review.passed:
                        semantic_errors = review.alignment_errors + review.coverage_errors + review.quiz_answerability_errors + review.activity_relevance_errors + review.split_progression_errors
                        raise ValueError("Semantic validation failed: " + "; ".join(semantic_errors or ["provider marked the module invalid"]))
                self.db.upsert_stage(job_id, lesson, week.actual_week, "docx_build", "running")
                output = build_module(self.settings.template, modules_dir, plan.course, bundle)
                self.db.upsert_stage(job_id, lesson, week.actual_week, "docx_build", "success")
                self.db.upsert_stage(job_id, lesson, week.actual_week, "validation", "running")
                audit = audit_docx(output)
                render = await asyncio.to_thread(render_verify, output, base / "render" / f"lesson-{lesson:02d}")
                if not audit["valid"] or (not render.get("valid") and not render.get("skipped")):
                    raise ValueError("; ".join(audit["errors"] + render.get("errors", [])))
                self.db.upsert_stage(job_id, lesson, week.actual_week, "validation", "success", "Structural and render conversion checks passed" if render.get("valid") else "Structural checks passed; render unavailable")
                generated.append({"lesson": lesson, "week": week.actual_week, "file": output.name, "audit": audit, "render": render})
                self.db.update_job(job_id, progress=int((index + 1) / len(weeks) * 100), message=f"Completed Lesson {lesson} of {len(weeks)}")
            (base / "normalized-syllabus.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            report_json(base / "validation-report.json", {"valid": True, "modules": generated})
            report_json(base / "generation-report.json", {"mode": "automatic", "module_count": len(generated), "expected_base_llm_calls_per_module": 5, "presentation_format": "markdown", "quiz_format": "aiken-style text", "activity_format": "markdown", "python_compiles_stage_json": True, "full_bundle_refinement": False})
            package_course(base)
            transition(self.settings.data_root, job_id, JobStatus.GENERATING, JobStatus.SUCCESS)
            self.db.update_job(job_id, status=JobStatus.SUCCESS, progress=100, message="All modules are ready", error="")
        except Exception as exc:
            dump_json(self.settings.data_root, False, f"{job_id}-generation-error", {"error": str(exc), "traceback": traceback.format_exc()})
            self.db.update_job(job_id, status=JobStatus.FAILED, error=str(exc), message="Generation stopped at a failed stage")


def validate_imported(settings: Settings, db: Database, job_id: str, raw: object) -> tuple[list[ModuleBundle], list[str]]:
    row = db.get_job(job_id)
    plan = NormalizedSyllabus.model_validate_json(row["normalized_json"])
    modules_raw = raw.get("modules", []) if isinstance(raw, dict) else []
    errors: list[str] = []
    bundles: list[ModuleBundle] = []
    for index, value in enumerate(modules_raw):
        bundle, item_errors = validate_bundle(value, settings.quiz_questions)
        if bundle:
            item_errors.extend(validate_bundle_against_plan(bundle, plan))
        if item_errors:
            errors.extend(f"Module {index + 1}: {e}" for e in item_errors)
        elif bundle:
            bundles.append(bundle)
    expected = len([w for w in plan.weeks if w.generate])
    if len(modules_raw) != expected:
        errors.append(f"Expected {expected} modules, received {len(modules_raw)}")
    return bundles, errors


def build_imported(settings: Settings, db: Database, job_id: str, raw: object) -> tuple[bool, list[str]]:
    row = db.get_job(job_id)
    plan = NormalizedSyllabus.model_validate_json(row["normalized_json"])
    bundles, errors = validate_imported(settings, db, job_id, raw)
    if errors:
        dump_json(settings.data_root, False, f"{job_id}-manual-import", {"errors": errors, "rejected": raw})
        return False, errors
    current = JobStatus(row["status"])
    if current in {JobStatus.REVIEW, JobStatus.INBOX}:
        base = transition(settings.data_root, job_id, current, JobStatus.APPROVED)
    else:
        base = job_dir(settings.data_root, job_id, JobStatus.APPROVED)
    db.update_job(job_id, status=JobStatus.GENERATING, mode="manual", message="Building imported modules")
    reports = []
    for bundle in bundles:
        path = build_module(settings.template, base / "modules", plan.course, bundle)
        audit = audit_docx(path)
        render = render_verify(path, base / "render" / f"lesson-{bundle.lesson_number:02d}")
        if not audit["valid"] or (not render.get("valid") and not render.get("skipped")):
            errors.extend(audit["errors"] + render.get("errors", []))
        reports.append({"audit": audit, "render": render})
    if errors:
        db.update_job(job_id, status=JobStatus.FAILED, error="; ".join(errors), message="Imported content built with validation failures")
        return False, errors
    (base / "normalized-syllabus.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    report_json(base / "validation-report.json", {"valid": True, "modules": reports})
    report_json(base / "generation-report.json", {"mode": "manual", "module_count": len(bundles), "llm_generation_calls": 0, "manual_refinement_required": True})
    package_course(base)
    transition(settings.data_root, job_id, JobStatus.GENERATING, JobStatus.SUCCESS)
    db.update_job(job_id, status=JobStatus.SUCCESS, progress=100, message="Imported modules are ready", error="")
    dump_json(settings.data_root, True, f"{job_id}-manual-import", raw)
    return True, []
