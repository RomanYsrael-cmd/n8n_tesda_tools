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
    font_family: str = "Times New Roman"
    font_size: float = Field(default=12, ge=8, le=24)
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


class RichTextSpan(BaseModel):
    text: str = Field(min_length=1)
    bold: bool = False
    italic: bool = False


class PresentationBlock(BaseModel):
    type: Literal["heading", "paragraph", "bullet", "numbered", "example", "note"]
    spans: list[RichTextSpan] = Field(min_length=1)

    @property
    def plain_text(self) -> str:
        return "".join(span.text for span in self.spans)


class ContentReference(BaseModel):
    title: str = Field(min_length=1)
    author_or_organization: str = ""
    year: str = ""
    url: str = ""


class PresentationContent(BaseModel):
    lesson_title: str
    information_sheet_title: str
    measurable_objectives: list[str] = Field(min_length=1)
    pre_assessment: list[str] = Field(min_length=1)
    introduction: str
    presentation: list[PresentationBlock] = Field(min_length=1)
    references: list[ContentReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def instructional_length(self):
        intro_words = len(self.introduction.split())
        if not 60 <= intro_words <= 100:
            raise ValueError(f"Introduction must contain 60-100 words; received {intro_words}")
        presentation_text = " ".join(block.plain_text for block in self.presentation)
        total_words = len((self.introduction + " " + presentation_text).split())
        if not 800 <= total_words <= 2000:
            raise ValueError(f"Presentation must contain 800-2000 words including the introduction; received {total_words}")
        forbidden = ["approved topic", "approved topics", "approved scope", "supplied json", "generated presentation"]
        found = [phrase for phrase in forbidden if phrase in presentation_text.casefold() or phrase in self.introduction.casefold()]
        if found:
            raise ValueError("Reader-facing presentation must not use internal workflow language: " + ", ".join(found))
        if not any(block.type == "example" for block in self.presentation):
            raise ValueError("Presentation must include at least one reader-friendly example")
        return self


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
        answers = [self.answer_key[qid] for qid in ids]
        if len(answers) >= 4:
            counts = {letter: answers.count(letter) for letter in "ABCD"}
            if any(count == 0 for count in counts.values()):
                raise ValueError("Quiz answers must use A, B, C, and D")
            if max(counts.values()) - min(counts.values()) > 1:
                raise ValueError("Quiz answer positions must be reasonably balanced across A, B, C, and D")
        if len(answers) >= 8 and all(answers[i] == "ABCD"[i % 4] for i in range(len(answers))):
            raise ValueError("Quiz answers must not use an obvious repeating A-B-C-D pattern")
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
        learner_text = " ".join([self.title, self.performance_objective, *self.steps, *self.performance_criteria]).casefold()
        if any(phrase in learner_text for phrase in ["approved scope", "approved topic", "supplied json", "generated presentation"]):
            raise ValueError("Let's Apply must not expose internal workflow language to learners")
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
    default_author: str = ""
    default_trainer: str = ""
    font_family: str = "Times New Roman"
    font_size: float = Field(default=12, ge=8, le=24)
