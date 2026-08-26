from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class JobStatus(StrEnum):
    INBOX = "inbox"
    NORMALIZING = "normalizing"
    REVIEW = "review"
    APPROVED = "approved"
    GENERATING = "generating"
    PAUSED = "paused"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class CourseMetadata(BaseModel):
    code: str = ""
    title: str
    description: str = ""
    author: str = ""
    trainer: str = ""
    outcomes: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class SourceTrace(BaseModel):
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None
    source_text: str = ""


class WeekPlan(BaseModel):
    actual_week: int = Field(ge=1)
    lesson_number: int | None = Field(default=None, ge=1)
    proposed_title: str
    learning_outcome: str = ""
    generate: bool = True
    type: Literal["instruction", "orientation", "examination", "other"] = "instruction"
    session: str = ""
    topic_scope: str = ""
    methods: list[str] = Field(default_factory=list)
    presentation_guidance: str = ""
    practice: str = ""
    feedback: str = ""
    resources: list[str] = Field(default_factory=list)
    skipped_reason: str = ""
    multi_week_source: str = ""
    warnings: list[str] = Field(default_factory=list)
    source_traceability: list[SourceTrace] = Field(default_factory=list)


class NormalizedSyllabus(BaseModel):
    schema_version: str = "1.0"
    source_filename: str
    course: CourseMetadata
    weeks: list[WeekPlan]
    normalization_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sequence_is_continuous(self):
        lessons = [w.lesson_number for w in self.weeks if w.generate]
        if lessons != list(range(1, len(lessons) + 1)):
            raise ValueError("Generated lessons must be numbered continuously from 1")
        if len({w.actual_week for w in self.weeks}) != len(self.weeks):
            raise ValueError("Actual week numbers must be unique")
        return self


class Choice(BaseModel):
    id: Literal["A", "B", "C", "D"]
    text: str = Field(min_length=1)


class QuizQuestion(BaseModel):
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    choices: list[Choice]
    answer: Literal["A", "B", "C", "D"]

    @model_validator(mode="after")
    def four_unique_choices(self):
        if len(self.choices) != 4 or {c.id for c in self.choices} != {"A", "B", "C", "D"}:
            raise ValueError("Each quiz item must have exactly choices A, B, C, and D")
        if len({c.text.strip().casefold() for c in self.choices}) != 4:
            raise ValueError("Quiz choices must be unique")
        return self


class PresentationContent(BaseModel):
    lesson_title: str
    measurable_objectives: list[str] = Field(min_length=1)
    pre_assessment: list[str] = Field(min_length=1)
    presentation: list[str] = Field(min_length=1)


class QuizContent(BaseModel):
    questions: list[QuizQuestion]
    answer_key: dict[str, Literal["A", "B", "C", "D"]]

    @model_validator(mode="after")
    def key_matches(self):
        ids = [q.id for q in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("Quiz question IDs must be unique")
        if set(ids) != set(self.answer_key):
            raise ValueError("Answer key must contain one entry for every question")
        if any(self.answer_key[q.id] != q.answer for q in self.questions):
            raise ValueError("Answer key entries must match question answers")
        normalized = [q.question.strip().casefold() for q in self.questions]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Quiz questions must not be duplicated")
        return self


class ApplyContent(BaseModel):
    title: str
    performance_objective: str
    supplies_materials: list[str]
    equipment: list[str]
    steps: list[str] = Field(min_length=1)
    assessment_method: str
    performance_criteria: list[str]

    @model_validator(mode="after")
    def exactly_five_criteria(self):
        if len(self.performance_criteria) != 5:
            raise ValueError("Let's Apply must have exactly five observable performance criteria")
        return self


class ModuleBundle(BaseModel):
    schema_version: str = "1.0"
    actual_week: int = Field(ge=1)
    lesson_number: int = Field(ge=1)
    approved_scope: str
    presentation: PresentationContent
    quiz: QuizContent
    practical_activity: ApplyContent


class SemanticReview(BaseModel):
    passed: bool
    alignment_errors: list[str] = Field(default_factory=list)
    coverage_errors: list[str] = Field(default_factory=list)
    quiz_answerability_errors: list[str] = Field(default_factory=list)
    activity_relevance_errors: list[str] = Field(default_factory=list)
    split_progression_errors: list[str] = Field(default_factory=list)


class ProviderConfig(BaseModel):
    provider: str = "openrouter"
    base_url: str = "https://openrouter.ai/api/v1"
    model: str = "openrouter/free"
    api_key: str = ""
    semantic_validation: bool = False
