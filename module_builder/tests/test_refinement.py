from docx import Document
from pydantic import ValidationError
import pytest

from app.docx_engine import build_module
from app.prompts import manual_refinement_prompt, refinement_prompt
from app.schemas import CourseMetadata, NormalizedSyllabus, WeekPlan
from conftest import TEMPLATE, make_bundle


def _plan():
    week = WeekPlan(actual_week=2, lesson_number=1, proposed_title="Introduction to AIS", topic_scope="Introduction to AIS")
    return NormalizedSyllabus(source_filename="sample.docx", course=CourseMetadata(title="AIS"), weeks=[week])


def test_presentation_enforces_introduction_and_total_word_counts(bundle):
    raw = bundle.presentation.model_dump()
    raw["introduction"] = "Too short"
    try:
        type(bundle.presentation).model_validate(raw)
        assert False, "short introduction should fail"
    except ValidationError as exc:
        assert "60-100 words" in str(exc)


def test_presentation_rejects_internal_workflow_language(bundle):
    raw = bundle.presentation.model_dump()
    raw["presentation"][1]["spans"][0]["text"] += " The approved scope is complete."
    with pytest.raises(ValidationError, match="internal workflow language"):
        type(bundle.presentation).model_validate(raw)


def test_presentation_rejects_duplicate_renderer_labels(bundle):
    raw = bundle.presentation.model_dump()
    example = next(block for block in raw["presentation"] if block["type"] == "example")
    example["spans"][0]["text"] = "Realistic example: A duplicated label"
    with pytest.raises(ValidationError, match="must not repeat an Example label"):
        type(bundle.presentation).model_validate(raw)


def test_refinement_prompts_require_key_facts_and_complete_json():
    plan = _plan()
    bundle = make_bundle(proposed_title="Introduction to AIS")
    prompt = refinement_prompt(plan, bundle)
    master = manual_refinement_prompt(plan, [bundle])
    assert "Key Facts 1.1 – Introduction to AIS" in prompt
    assert "60-100 words" in prompt and "800-2000 words" in prompt
    assert "single `modules` array" in master


def test_docx_uses_selected_font(tmp_path):
    course = CourseMetadata(title="AIS", font_family="Arial", font_size=11)
    path = build_module(TEMPLATE, tmp_path, course, make_bundle())
    doc = Document(path)
    runs = [run for paragraph in doc.paragraphs for run in paragraph.runs if run.text.strip()]
    assert runs
    assert all(run.font.name == "Arial" and run.font.size.pt == 11 for run in runs)
    assert any(run.bold and "Core concepts" in run.text for run in runs)
    assert any(run.italic and "retail business" in run.text for run in runs)
