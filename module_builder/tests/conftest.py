from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas import ApplyContent, Choice, ModuleBundle, PresentationContent, QuizContent, QuizQuestion


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template" / "Module Template.docx"
SYLLABUS = ROOT / "sample syllabus" / "AE17 Accounting Information System.docx"


def make_bundle(week: int = 2, lesson: int = 1, scope: str = "Introduction to AIS", count: int = 10) -> ModuleBundle:
    presentation = PresentationContent(
        lesson_title=f"AIS Lesson {lesson}",
        measurable_objectives=["Explain the approved AIS concepts", "Apply the concepts to a business case"],
        pre_assessment=["What information does an accounting system process?"],
        presentation=[f"The approved scope is {scope}.", "Accounting information systems collect, process, store, and report business data for decisions."],
    )
    questions = []
    key = {}
    for i in range(1, count + 1):
        qid = f"Q{i}"
        questions.append(QuizQuestion(id=qid, question=f"Which AIS statement is correct for business data item {i}?", choices=[Choice(id="A", text="It processes useful business data"), Choice(id="B", text="It removes all source records"), Choice(id="C", text="It prevents every error automatically"), Choice(id="D", text="It replaces all business decisions")], answer="A"))
        key[qid] = "A"
    practical = ApplyContent(
        title="Map an AIS process",
        performance_objective="Create an accurate process map from source document to report.",
        supplies_materials=["Case worksheet", "Paper"], equipment=["Computer"],
        steps=["Read the business case", "Identify inputs", "Map processing steps", "Identify outputs", "Check the map against the case"],
        assessment_method="Direct observation and output review",
        performance_criteria=["Identifies the required source data", "Sequences processing steps correctly", "Labels outputs accurately", "Connects each output to the approved scope", "Submits a complete and readable process map"],
    )
    return ModuleBundle(actual_week=week, lesson_number=lesson, approved_scope=scope, presentation=presentation, quiz=QuizContent(questions=questions, answer_key=key), practical_activity=practical)


@pytest.fixture
def bundle():
    return make_bundle()

