from __future__ import annotations

import asyncio
import json
import traceback
from pathlib import Path

from pydantic import ValidationError

from .config import Settings
from .database import Database
from .docx_engine import build_module, package_course
from .prompts import refinement_prompt, repair_prompt, semantic_validation_prompt, stage_prompt
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

    def start(self, job_id: str):
        current = self.tasks.get(job_id)
        if current and not current.done():
            return
        self.db.set_control(job_id, pause=False, cancel=False)
        self.tasks[job_id] = asyncio.create_task(self.run_auto(job_id))

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
                presentation = await self._validated_call(job_id, lesson, week.actual_week, "presentation", stage_prompt(plan, week, "presentation"), PresentationContent)
                quiz_task = self._validated_call(job_id, lesson, week.actual_week, "quiz", stage_prompt(plan, week, "quiz", presentation.model_dump(), self.settings.quiz_questions), QuizContent)
                apply_task = self._validated_call(job_id, lesson, week.actual_week, "practical_activity", stage_prompt(plan, week, "practical_activity", presentation.model_dump()), ApplyContent)
                quiz, practical = await asyncio.gather(quiz_task, apply_task)
                bundle = ModuleBundle(actual_week=week.actual_week, lesson_number=lesson, approved_scope=week.topic_scope, presentation=presentation, quiz=quiz, practical_activity=practical)
                bundle = await self._validated_call(job_id, lesson, week.actual_week, "content_refinement", refinement_prompt(plan, bundle), ModuleBundle)
                validated, errors = validate_bundle(bundle.model_dump(), self.settings.quiz_questions)
                errors += validate_bundle_against_plan(bundle, plan)
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
            report_json(base / "generation-report.json", {"mode": "automatic", "module_count": len(generated), "expected_base_llm_calls_per_module": 4, "refinement_required": True})
            package_course(base)
            transition(self.settings.data_root, job_id, JobStatus.GENERATING, JobStatus.SUCCESS)
            self.db.update_job(job_id, status=JobStatus.SUCCESS, progress=100, message="All modules are ready")
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
    db.update_job(job_id, status=JobStatus.SUCCESS, progress=100, message="Imported modules are ready")
    dump_json(settings.data_root, True, f"{job_id}-manual-import", raw)
    return True, []
