from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class CBLMTopic(BaseModel):
    number: int = Field(ge=1)
    title: str
    weeks: list[int] = Field(min_length=1)
    learning_objectives: str = ""
    keyfacts_content: str = ""
    quiz_instructions: str = ""
    quiz: str = ""
    answer_key: str = ""
    activity_title: str = ""
    activity_objectives: str = ""
    activity_supplies: str = ""
    activity_equipment: str = ""
    activity_steps: str = ""
    activity_method: str = ""
    activity_criteria: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    source_material: str = ""
    methods: list[str] = Field(default_factory=list)
    guidance: str = ""
    include: bool = True


class CBLMLearningOutcome(BaseModel):
    number: int = Field(ge=1)
    learning_outcome: str
    next_learning_outcome: str = ""
    module_title: str = ""
    module_descriptor: str = ""
    duration: float = Field(ge=0.5, le=10000)
    location: str = ""
    laboratory: str = ""
    training_materials: list[str] = Field(default_factory=list)
    topics: list[CBLMTopic] = Field(min_length=1)

    @model_validator(mode="after")
    def topic_numbers_are_continuous(self):
        expected = list(range(1, len(self.topics) + 1))
        if [topic.number for topic in self.topics] != expected:
            raise ValueError("Topic numbers must be continuous from 1")
        return self


class CBLMCourse(BaseModel):
    sector: str = ""
    course_title: str
    course_code: str = ""
    name: str = ""
    font_family: str = "Bookman Old Style"
    font_size: float = Field(default=12, ge=8, le=36)


class CBLMPlan(BaseModel):
    schema_version: str = "1.0"
    source_filename: str
    course: CBLMCourse
    learning_outcomes: list[CBLMLearningOutcome] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def outcome_numbers_are_continuous(self):
        expected = list(range(1, len(self.learning_outcomes) + 1))
        if [outcome.number for outcome in self.learning_outcomes] != expected:
            raise ValueError("Learning outcome numbers must be continuous from 1")
        return self
