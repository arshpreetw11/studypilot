"""Pydantic request/response models shared by the API."""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Topic(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    difficulty: int = Field(default=2, ge=1, le=3, description="1 easy, 2 medium, 3 hard")
    hours: float = Field(default=2.0, gt=0, le=40, description="Estimated first-pass study hours")
    mastery: float = Field(default=0.0, ge=0, le=1, description="0 = new, 1 = fully mastered")
    completed_hours: float = Field(default=0.0, ge=0, description="Learning hours already done")


class Subject(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    exam_date: date
    topics: list[Topic] = Field(min_length=1)


class PlanRequest(BaseModel):
    subjects: list[Subject] = Field(min_length=1, max_length=12)
    start_date: date
    hours_per_day: float = Field(default=4.0, ge=0.5, le=14)
    rest_weekdays: list[int] = Field(default_factory=list, description="0=Mon ... 6=Sun")
    first_day_used_hours: float = Field(default=0, ge=0, le=14, description="Hours already studied on start_date (replans)")

    @field_validator("rest_weekdays")
    @classmethod
    def _valid_weekdays(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("rest_weekdays must be between 0 (Mon) and 6 (Sun)")
        if len(set(v)) >= 7:
            raise ValueError("You need at least one study day per week")
        return sorted(set(v))


TaskType = Literal["learn", "review", "revision", "exam"]


class StudyTask(BaseModel):
    id: str
    type: TaskType
    subject: str
    topic: str | None = None
    hours: float
    note: str = ""


class PlanDay(BaseModel):
    date: date
    is_rest: bool = False
    tasks: list[StudyTask] = Field(default_factory=list)

    @property
    def load(self) -> float:
        return sum(t.hours for t in self.tasks if t.type != "exam")


class SubjectSummary(BaseModel):
    subject: str
    exam_date: date
    planned_hours: float
    unscheduled_hours: float
    days_until_exam: int


class PlanResponse(BaseModel):
    days: list[PlanDay]
    summaries: list[SubjectSummary]
    warnings: list[str]
    total_hours: float


class SyllabusText(BaseModel):
    text: str = Field(min_length=3, max_length=40_000)


class ParsedSyllabus(BaseModel):
    subjects: list[dict]
    source: Literal["ai", "heuristic"]


class QuizRequest(BaseModel):
    subject: str
    topic: str
    mastery: float = Field(default=0.0, ge=0, le=1)
    num_questions: int = Field(default=5, ge=1, le=10)


class QuizQuestion(BaseModel):
    question: str
    options: list[str]
    answer_index: int | None = None  # None => self-assessed question
    explanation: str = ""


class QuizResponse(BaseModel):
    subject: str
    topic: str
    questions: list[QuizQuestion]
    source: Literal["ai", "offline"]


class ExplainRequest(BaseModel):
    subject: str
    topic: str
    question: str | None = Field(default=None, max_length=1000)
    mastery: float = Field(default=0.0, ge=0, le=1)


class ExplainResponse(BaseModel):
    markdown: str
    source: Literal["ai", "offline"]


class CoachRequest(BaseModel):
    plan: PlanResponse
    today: date
    completed_task_ids: list[str] = Field(default_factory=list)
    weak_topics: list[str] = Field(default_factory=list)


class CoachResponse(BaseModel):
    message: str
    source: Literal["ai", "offline"]
