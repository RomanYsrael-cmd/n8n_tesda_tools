import pytest
from pydantic import ValidationError

from app.schemas import ApplyContent, Choice, QuizContent, QuizQuestion
from app.validation import validate_bundle


def test_quiz_validation(bundle):
    valid, errors = validate_bundle(bundle.model_dump(), 10)
    assert valid is not None
    assert errors == []


def test_quiz_rejects_wrong_choice_count():
    with pytest.raises(ValidationError):
        QuizQuestion(id="Q1", question="Question?", choices=[Choice(id="A", text="One")], answer="A")


def test_quiz_rejects_key_mismatch(bundle):
    raw = bundle.quiz.model_dump()
    raw["answer_key"].pop("Q1")
    with pytest.raises(ValidationError):
        QuizContent.model_validate(raw)


def test_quiz_rejects_generic_all_a_answer_key(bundle):
    raw = bundle.quiz.model_dump()
    for question in raw["questions"]:
        question["answer"] = "A"
        raw["answer_key"][question["id"]] = "A"
    with pytest.raises(ValidationError, match="must use A, B, C, and D"):
        QuizContent.model_validate(raw)


def test_apply_requires_exactly_five_criteria():
    with pytest.raises(ValidationError):
        ApplyContent(title="x", performance_objective="x", supplies_materials=[], equipment=[], steps=["x"], assessment_method="x", performance_criteria=["one"])
