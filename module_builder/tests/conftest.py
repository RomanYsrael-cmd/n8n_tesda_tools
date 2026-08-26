from __future__ import annotations

from pathlib import Path

import pytest

from app.schemas import ApplyContent, Choice, ModuleBundle, PresentationBlock, PresentationContent, QuizContent, QuizQuestion, RichTextSpan


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template" / "Module Template.docx"
SYLLABUS = ROOT / "sample syllabus" / "AE17 Accounting Information System.docx"


def make_bundle(week: int = 2, lesson: int = 1, scope: str = "Introduction to AIS", count: int = 10, proposed_title: str | None = None) -> ModuleBundle:
    proposed_title = proposed_title or f"AIS Lesson {lesson}"
    introduction = " ".join(["This lesson introduces approved accounting information system concepts through clear workplace examples and guided explanations for beginning learners."] * 4)
    content = f"This lesson examines {scope}. " + " ".join(["Accounting information systems collect process store and report business data for accurate workplace decisions and reliable organizational operations."] * 55)
    presentation = PresentationContent(
        lesson_title=f"AIS Lesson {lesson}",
        information_sheet_title=f"Key Facts {lesson}.1 – {proposed_title}",
        measurable_objectives=["Explain essential AIS concepts", "Apply the concepts to a business case"],
        pre_assessment=["What information does an accounting system process?"],
        introduction=introduction,
        presentation=[PresentationBlock(type="heading", spans=[RichTextSpan(text="Core concepts")]), PresentationBlock(type="paragraph", spans=[RichTextSpan(text=content, bold=False)]), PresentationBlock(type="example", spans=[RichTextSpan(text="A retail business records a sale, updates inventory, posts the receivable, and produces a management report.", italic=True)])],
        references=[],
    )
    questions = []
    key = {}
    answer_pattern = ["A", "B", "D", "C", "B", "A", "C", "D", "A", "B"]
    for i in range(1, count + 1):
        qid = f"Q{i}"
        answer = answer_pattern[i - 1]
        choices = {letter: f"Distractor {letter} for item {i}" for letter in "ABCD"}
        choices[answer] = "It processes useful business data"
        questions.append(QuizQuestion(id=qid, question=f"Which AIS statement is correct for business data item {i}?", choices=[Choice(id=letter, text=choices[letter]) for letter in "ABCD"], answer=answer))
        key[qid] = answer
    practical = ApplyContent(
        title="Map an AIS process",
        performance_objective="Create an accurate process map from source document to report.",
        supplies_materials=["Case worksheet", "Paper"], equipment=["Computer"],
        steps=["Read the business case", "Identify inputs", "Map processing steps", "Identify outputs", "Check the map against the case"],
        assessment_method="Direct observation and output review",
        performance_criteria=["Identifies the required source data", "Sequences processing steps correctly", "Labels outputs accurately", "Connects each output to the business case", "Submits a complete and readable process map"],
    )
    return ModuleBundle(actual_week=week, lesson_number=lesson, approved_scope=scope, presentation=presentation, quiz=QuizContent(questions=questions, answer_key=key), practical_activity=practical)


@pytest.fixture
def bundle():
    return make_bundle()
