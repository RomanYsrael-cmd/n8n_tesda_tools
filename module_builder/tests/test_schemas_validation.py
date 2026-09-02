import pytest
from pydantic import ValidationError

from app.schemas import ApplyContent, Choice, ModuleBundle, QuizContent, QuizQuestion
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


def test_quiz_allows_relevant_choices_to_recur_across_questions(bundle):
    raw = bundle.quiz.model_dump()
    raw["questions"][1]["choices"][0]["text"] = raw["questions"][0]["choices"][0]["text"]
    assert QuizContent.model_validate(raw)


def test_quiz_allows_long_choices_and_uneven_answer_distribution(bundle):
    raw = bundle.quiz.model_dump()
    raw["questions"][0]["choices"][0]["text"] = " ".join(["detailed"] * 31)
    answers = ["A", "A", "A", "A", "A", "A", "A", "B", "C", "D"]
    for question, answer in zip(raw["questions"], answers):
        question["answer"] = answer
        raw["answer_key"][question["id"]] = answer
    assert QuizContent.model_validate(raw)


def test_bundle_does_not_apply_keyword_answerability_heuristic(bundle):
    raw = bundle.model_dump()
    raw["quiz"]["questions"][0]["question"] = "How should photosynthesis be evaluated on Mars?"
    valid, errors = validate_bundle(raw, 10)
    assert valid is not None
    assert errors == []
    raw = bundle.quiz.model_dump()
    raw["questions"][0]["question"] = "Which statement best captures the meaning of AIS?"
    with pytest.raises(ValidationError, match="specific and varied"):
        QuizContent.model_validate(raw)


def test_automatic_bundle_preserves_context_when_nested_presentation_is_revalidated(bundle):
    raw = bundle.model_dump()
    raw["presentation"]["introduction"] = "A concise API-generated introduction."
    raw["presentation"]["presentation"] = [
        block for block in raw["presentation"]["presentation"] if block["type"] != "example"
    ]

    rebuilt = ModuleBundle.model_validate(raw, context={"automatic": True})

    assert rebuilt.presentation.introduction == "A concise API-generated introduction."
    assert all(block.type != "example" for block in rebuilt.presentation.presentation)


def test_apply_requires_exactly_five_criteria():
    with pytest.raises(ValidationError):
        ApplyContent(title="x", performance_objective="x", supplies_materials=[], equipment=[], steps=["x"], assessment_method="x", performance_criteria=["one"])
