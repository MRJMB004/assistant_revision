"""
Schémas Pydantic (v2) utilisés pour valider les entrées/sorties de l'API.
"""
import datetime
from typing import List, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


# ---------- User ----------
class UserCreate(BaseModel):
    name: str
    email: EmailStr


class UserRegister(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Module ----------
class ModuleCreate(BaseModel):
    name: str
    course: Optional[str] = None
    weekly_objective_hours: float = 2.0


class ModuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    course: Optional[str] = None
    weekly_objective_hours: float


# ---------- Quiz ----------
class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    choices: List[str]
    difficulty: Optional[str] = None
    level: int = 1


class AnswerIn(BaseModel):
    question_id: int = Field(gt=0)
    selected_index: int = Field(ge=0)


class QuizSubmit(BaseModel):
    answers: List[AnswerIn] = Field(min_length=1, max_length=100)
    level: Optional[int] = Field(default=None, ge=1, le=50)
    course_id: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def answer_ids_must_be_unique(self):
        question_ids = [answer.question_id for answer in self.answers]
        if len(question_ids) != len(set(question_ids)):
            raise ValueError("Chaque question ne peut etre repondue qu'une fois.")
        return self


class QuestionResultOut(BaseModel):
    question_id: int
    question: str
    selected_index: int
    selected_answer: str
    is_correct: bool
    correct_answer: str
    explanation: str


class QuizResult(BaseModel):
    module_id: int
    score: float
    correct: int
    incorrect: int
    total: int
    diagnostic: str
    results: List[QuestionResultOut]
    level: Optional[int] = None
    passed: Optional[bool] = None
    next_level_unlocked: Optional[bool] = None
    course_id: Optional[int] = None
    consolidated_count: int = 0
    remaining_review_count: int = 0


class QuizAttemptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_id: int
    user_id: int
    date: datetime.datetime
    score: float
    correct_count: Optional[int] = None
    total_questions: Optional[int] = None
    results: Optional[List[QuestionResultOut]] = None
    level: Optional[int] = None
    passed: Optional[bool] = None
    course_id: Optional[int] = None


class QuizStatsOut(BaseModel):
    module_id: int
    user_id: int
    attempt_count: int
    average_score: Optional[float] = None
    best_score: Optional[float] = None
    level_reached: int = 1
    best_by_level: List["LevelBestOut"] = Field(default_factory=list)
    course_id: Optional[int] = None


class ReviewItemOut(BaseModel):
    question_id: int
    notion: str
    mistake_count: int
    correct_answer: str
    explanation: str


class LevelBestOut(BaseModel):
    level: int
    best_score: Optional[float] = None
    best_correct: Optional[int] = None
    total_questions: Optional[int] = None
    passed: bool = False


class QuizLevelOut(LevelBestOut):
    unlocked: bool
    current: bool


class QuizLevelsOut(BaseModel):
    module_id: int
    course_id: int
    max_unlocked_level: int
    levels: List[QuizLevelOut]


class QuizLevelStartRequest(BaseModel):
    course_id: Optional[int] = Field(default=None, gt=0)


class QuizLevelSessionOut(BaseModel):
    module_id: int
    course_id: int
    level: int
    questions: List[QuestionOut]


# ---------- Cours et quiz generes par IA ----------
class CourseGenerateRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    level: str = Field(min_length=2, max_length=80)
    language: str = Field(min_length=2, max_length=80)
    desired_length: int = Field(ge=300, le=10_000)
    objectives: List[str] = Field(min_length=1, max_length=10)
    chapters: List[str] = Field(default_factory=list, max_length=12)


class CourseChapter(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1)
    examples: List[str] = Field(default_factory=list)


class GeneratedCourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    module_id: int
    subject: str
    level: str
    language: str
    desired_length: int
    objectives: List[str]
    chapters: List[CourseChapter]
    content: str
    summary: str
    created_at: datetime.datetime
    ai_generated: str


class CourseUpdateRequest(BaseModel):
    subject: str = Field(min_length=2, max_length=200)
    content: Optional[str] = Field(default=None, min_length=1)


class CourseMoveRequest(BaseModel):
    module_id: int = Field(gt=0)


class QuizGenerateRequest(BaseModel):
    question_count: int = Field(ge=1, le=20)
    difficulty: str = Field(pattern="^(facile|moyen|difficile)$")
    level: int = Field(default=1, ge=1, le=50)


class GeneratedQuizQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)
    choices: List[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)
    explanation: str = Field(min_length=1, max_length=4_000)
    notion_key: str = Field(min_length=1, max_length=120)

    @field_validator("choices")
    @classmethod
    def choices_must_be_distinct(cls, choices: List[str]) -> List[str]:
        cleaned = [choice.strip() for choice in choices]
        if any(not choice for choice in cleaned) or len(set(cleaned)) != 4:
            raise ValueError("Les quatre choix doivent etre distincts et non vides.")
        return cleaned


# ---------- Plan ----------
class PlanGenerateRequest(BaseModel):
    total_hours_per_week: float
    days_per_week: int = 6


class PlanSlot(BaseModel):
    day: str
    module_id: int
    module_name: str
    hours: float
    priority: str


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime.datetime
    total_hours_per_week: float
    days_per_week: int
    entries: List[PlanSlot]


# ---------- Notifications ----------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sent_at: datetime.datetime
    subject: str
    body: str
    simulated: str


# ---------- Resources ----------
class ResourceOut(BaseModel):
    title: str
    url: str
    type: str


# ---------- Retention ----------
class RetentionHistoryItem(BaseModel):
    date: datetime.datetime
    score: float


class RetentionOut(BaseModel):
    module_id: int
    module_name: str
    history: List[RetentionHistoryItem] = Field(default_factory=list)
    last_score: Optional[float] = None
    interval_days: int
    next_review: Optional[datetime.date] = None
    ef: float = 2.5
    reps: int = 0
    days_since: Optional[int] = None
    retention: Optional[float] = None
    overdue_days: int = 0
