"""
Assistant de révisions personnalisé — API FastAPI.

Lancer avec :  uvicorn main:app --port 8000
Documentation interactive : http://localhost:8000/docs

Pour activer les ressources par IA (optionnel) :
    pip install google-genai
    set GEMINI_API_KEY=ta_cle           (Windows)
    export GEMINI_API_KEY=ta_cle        (Mac/Linux)
"""
import os
import re
import unicodedata
from difflib import SequenceMatcher
from datetime import date
import datetime
from email.message import EmailMessage
import smtplib
import ssl
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from sqlalchemy.orm import Session

import models
import schemas
from auth import create_access_token, get_current_user, hash_password, verify_password
from database import engine, get_db, migrate_schema
from algorithm import (
    AIConfigurationError,
    AIGenerationError,
    generate_plan,
    generate_course_ai,
    generate_quiz_ai,
    compute_retention,
    recommend_resources,
    recommend_resources_ai,
)

models.Base.metadata.create_all(bind=engine)
migrate_schema()

app = FastAPI(
    title="Assistant de révisions personnalisé",
    description="Plan de révision adaptatif basé sur des quiz diagnostiques et une règle 'faiblesses d'abord'.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Utilisateurs
# ---------------------------------------------------------------------------
@app.post("/auth/register", response_model=schemas.AuthResponse, status_code=201)
def register(user: schemas.UserRegister, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(409, "Cette adresse e-mail est deja utilisee")
    db_user = models.User(
        name=user.name.strip(),
        email=user.email,
        password_hash=hash_password(user.password),
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return schemas.AuthResponse(access_token=create_access_token(db_user.id), user=db_user)


@app.post("/auth/login", response_model=schemas.AuthResponse)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not user.password_hash or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect")
    return schemas.AuthResponse(access_token=create_access_token(user.id), user=user)


@app.get("/auth/me", response_model=schemas.UserOut)
def current_user(current_user: models.User = Depends(get_current_user)):
    return current_user


@app.post("/users", response_model=schemas.UserOut)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Compatibilite legacy : cree un profil non connectable sans mot de passe."""
    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        return existing
    db_user = models.User(name=user.name, email=user.email)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@app.get("/users", response_model=List[schemas.UserOut], deprecated=True)
def list_users(current_user: models.User = Depends(get_current_user)):
    """Conserve la route historique sans exposer la liste des comptes."""
    return [current_user]


def _owned_module(db: Session, module_id: int, current_user: models.User) -> models.Module:
    module = db.get(models.Module, module_id)
    if not module:
        raise HTTPException(404, "Module introuvable")
    if module.user_id != current_user.id:
        raise HTTPException(403, "Ce module n'appartient pas a cet utilisateur")
    return module


def _owned_course(db: Session, course_id: int, current_user: models.User) -> models.GeneratedCourse:
    course = db.get(models.GeneratedCourse, course_id)
    if not course:
        raise HTTPException(404, "Cours genere introuvable")
    _owned_module(db, course.module_id, current_user)
    return course


QUIZ_LEVEL_COUNT = 50
QUIZ_QUESTIONS_PER_LEVEL = 5
QUIZ_PASS_SCORE = 80
MAX_NOTION_REVIEW_COUNT = 3


def _question_key(question: str) -> str:
    return re.sub(r"\W+", "", question).lower()


def _normalize_notion_key(value: str, fallback: str = "") -> str:
    normalized = unicodedata.normalize("NFKD", (value or fallback).strip())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized.lower()).strip("-")
    return normalized[:120] or "notion-generale"


def _similar_legacy_notions(left: str, right: str) -> bool:
    """Regroupe les anciennes questions identiques ou presque identiques."""
    left_key = _normalize_notion_key(left)
    right_key = _normalize_notion_key(right)
    if left_key == right_key:
        return True
    stop_words = {"a", "au", "aux", "ce", "ces", "comment", "d", "de", "des", "du", "en", "est", "et", "la", "le", "les", "l", "ou", "quel", "quelle", "quelles", "un", "une"}
    left_tokens = set(left_key.split("-")) - stop_words
    right_tokens = set(right_key.split("-")) - stop_words
    overlap = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    return (len(left_tokens & right_tokens) >= 2 and overlap >= 0.5) or SequenceMatcher(None, left_key, right_key).ratio() >= 0.86


def _legacy_notion_key(
    label: str, course_id: int, known_notions: dict[int, list[tuple[str, str]]]
) -> str:
    for notion_key, existing_label in known_notions.setdefault(course_id, []):
        if _similar_legacy_notions(label, existing_label):
            return notion_key
    notion_key = _normalize_notion_key(label)
    known_notions[course_id].append((notion_key, label))
    return notion_key


def _review_statuses(
    db: Session, user_id: int, course_id: int, limit: Optional[int] = None
) -> list[models.NotionStatus]:
    query = (
        db.query(models.NotionStatus)
        .filter(
            models.NotionStatus.user_id == user_id,
            models.NotionStatus.course_id == course_id,
            models.NotionStatus.review_count > 0,
        )
        .order_by(models.NotionStatus.review_count.desc(), models.NotionStatus.updated_at.desc())
    )
    return query.limit(limit).all() if limit else query.all()


def _update_notion_status(
    db: Session,
    user_id: int,
    course: models.GeneratedCourse,
    question: models.QuizQuestion,
    is_correct: bool,
    correct_answer: str,
    explanation: str,
) -> bool:
    notion_key = _normalize_notion_key(question.notion_key or question.question, question.question)
    question.notion_key = notion_key
    status = (
        db.query(models.NotionStatus)
        .filter(
            models.NotionStatus.user_id == user_id,
            models.NotionStatus.course_id == course.id,
            models.NotionStatus.notion_key == notion_key,
        )
        .first()
    )
    if status is None:
        status = models.NotionStatus(
            user_id=user_id,
            course_id=course.id,
            notion_key=notion_key,
            notion_label=question.question,
            correct_answer=correct_answer,
            explanation=explanation,
            review_count=0,
        )
        db.add(status)
        # La session SQLite n'active pas l'autoflush : la notion doit etre visible
        # des la reponse suivante du meme quiz.
        db.flush()
    else:
        status.correct_answer = correct_answer
        status.explanation = explanation

    previous_count = status.review_count
    status.review_count = (
        max(0, previous_count - 1)
        if is_correct
        else min(MAX_NOTION_REVIEW_COUNT, previous_count + 1)
    )
    return is_correct and previous_count > 0 and status.review_count == 0


def _migrate_notion_tracking() -> None:
    """Reconstruit les statuts depuis les reponses, sans supprimer l'historique."""
    db = next(get_db())
    try:
        questions = db.query(models.QuizQuestion).all()
        questions_by_id = {question.id: question for question in questions}
        for question in questions:
            if not question.notion_key:
                question.notion_key = _normalize_notion_key(question.question)

        balances = {}
        known_legacy_notions: dict[int, list[tuple[str, str]]] = {}
        attempts = (
            db.query(models.QuizAttempt)
            .filter(models.QuizAttempt.course_id.is_not(None))
            .order_by(models.QuizAttempt.date.asc(), models.QuizAttempt.id.asc())
            .all()
        )
        for attempt in attempts:
            result_course_ids = set()
            for result in attempt.results or []:
                question = questions_by_id.get(result.get("question_id"))
                # Une ancienne tentative peut avoir ete rattachee au dernier cours
                # du module. La question, elle, connait son cours reel.
                result_course_id = (
                    question.generated_course_id
                    if question and question.generated_course_id is not None
                    else attempt.course_id
                )
                if result_course_id is None:
                    continue
                result_course_ids.add(result_course_id)
                label = result.get("question", "Notion a consolider")
                current_key = (question.notion_key if question else "") or result.get("notion_key", "")
                question_derived_key = _normalize_notion_key(question.question) if question else ""
                if current_key and current_key != question_derived_key:
                    notion_key = _normalize_notion_key(current_key, label)
                else:
                    notion_key = _legacy_notion_key(label, result_course_id, known_legacy_notions)
                if question:
                    question.notion_key = notion_key
                result["notion_key"] = notion_key
                key = (attempt.user_id, result_course_id, notion_key)
                item = balances.setdefault(
                    key,
                    {
                        "count": 0,
                        "label": label,
                        "correct_answer": result.get("correct_answer", ""),
                        "explanation": result.get("explanation", ""),
                    },
                )
                item["count"] = (
                    max(0, item["count"] - 1)
                    if result.get("is_correct")
                    else min(MAX_NOTION_REVIEW_COUNT, item["count"] + 1)
                )
            if attempt.results:
                attempt.results = attempt.results

            # Corrige sans ambiguite les tentatives composees d'un seul cours.
            if len(result_course_ids) == 1:
                attempt.course_id = result_course_ids.pop()

        db.query(models.NotionStatus).delete(synchronize_session=False)
        for (user_id, course_id, notion_key), item in balances.items():
            db.add(
                models.NotionStatus(
                    user_id=user_id,
                    course_id=course_id,
                    notion_key=notion_key,
                    notion_label=item["label"],
                    correct_answer=item["correct_answer"],
                    explanation=item["explanation"],
                    review_count=item["count"],
                )
            )
        db.commit()
    finally:
        db.close()


_migrate_notion_tracking()


def _difficulty_for_level(level: int) -> str:
    if level == 1:
        return "facile"
    if level == 2:
        return "moyen"
    return "difficile"


def _progress_for_course(db: Session, user_id: int, course: models.GeneratedCourse) -> models.QuizProgress:
    progress = (
        db.query(models.QuizProgress)
        .filter(
            models.QuizProgress.user_id == user_id,
            models.QuizProgress.course_id == course.id,
        )
        .first()
    )
    if progress is None:
        progress = models.QuizProgress(
            user_id=user_id, module_id=course.module_id, course_id=course.id, max_unlocked_level=1
        )
        db.add(progress)
        db.flush()
    return progress


def _require_unlocked_level(
    db: Session, course: models.GeneratedCourse, level: int, current_user: models.User
) -> models.QuizProgress:
    if not 1 <= level <= QUIZ_LEVEL_COUNT:
        raise HTTPException(400, "Niveau de quiz invalide")
    progress = _progress_for_course(db, current_user.id, course)
    if level > progress.max_unlocked_level:
        raise HTTPException(403, "Ce niveau est verrouille. Reussis le niveau precedent.")
    return progress


def _shown_question_ids(db: Session, user_id: int, course_id: int, level: int) -> set[int]:
    return {
        question_id
        for (question_id,) in db.query(models.QuizQuestionExposure.question_id)
        .filter(
            models.QuizQuestionExposure.user_id == user_id,
            models.QuizQuestionExposure.course_id == course_id,
            models.QuizQuestionExposure.level == level,
        )
        .all()
    }


def _generate_level_questions(
    db: Session,
    course: models.GeneratedCourse,
    level: int,
    current_user: models.User,
) -> list[models.QuizQuestion]:
    shown_ids = _shown_question_ids(db, current_user.id, course.id, level)
    avoided = [
        question
        for (question,) in db.query(models.QuizQuestion.question)
        .join(
            models.QuizQuestionExposure,
            models.QuizQuestionExposure.question_id == models.QuizQuestion.id,
        )
        .filter(
            models.QuizQuestionExposure.user_id == current_user.id,
            models.QuizQuestionExposure.course_id == course.id,
            models.QuizQuestionExposure.level == level,
        )
        .all()
    ]
    review_notions = [
        {
            "notion_key": status.notion_key,
            "notion_label": status.notion_label,
            "correct_answer": status.correct_answer,
        }
        for status in _review_statuses(db, current_user.id, course.id, limit=2)
    ]
    try:
        generated = generate_quiz_ai(
            course_content=course.content,
            language=course.language,
            question_count=QUIZ_QUESTIONS_PER_LEVEL,
            difficulty=_difficulty_for_level(level),
            level=level,
            avoided_questions=avoided,
            review_notions=review_notions,
        )
        validated = [schemas.GeneratedQuizQuestion.model_validate(item) for item in generated]
    except (AIConfigurationError, AIGenerationError) as exc:
        raise _ai_http_error(exc) from exc
    except (TypeError, ValidationError, ValueError) as exc:
        raise HTTPException(502, "La reponse IA ne respecte pas le format attendu.") from exc

    keys = [_question_key(item.question) for item in validated]
    recall_keys = {item["notion_key"] for item in review_notions}
    for item in validated:
        item.notion_key = _normalize_notion_key(item.notion_key, item.question)
    if len(validated) != QUIZ_QUESTIONS_PER_LEVEL or len(keys) != len(set(keys)):
        raise HTTPException(502, "La generation IA contient des questions dupliquees ou incompletes.")
    if set(keys) & {_question_key(question) for question in avoided}:
        raise HTTPException(502, "La generation IA a reutilise une question deja posee.")
    recall_count = sum(item.notion_key in recall_keys for item in validated)
    if review_notions and not 1 <= recall_count <= 2:
        raise HTTPException(502, "La generation IA n'a pas inclus les questions de rappel demandees.")

    records = [
        models.QuizQuestion(
            module_id=course.module_id,
            generated_course_id=course.id,
            question=item.question,
            choices=item.choices,
            correct_index=item.correct_index,
            explanation=item.explanation,
            difficulty=_difficulty_for_level(level),
            level=level,
            notion_key=item.notion_key,
        )
        for item in validated
    ]
    db.add_all(records)
    db.flush()
    return records


# ---------------------------------------------------------------------------
# Modules / cours
# ---------------------------------------------------------------------------
@app.post("/modules", response_model=schemas.ModuleOut)
def create_module(
    module: schemas.ModuleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    db_module = models.Module(user_id=current_user.id, **module.model_dump())
    db.add(db_module)
    db.commit()
    db.refresh(db_module)
    return db_module


@app.get("/modules", response_model=List[schemas.ModuleOut])
def list_modules(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return db.query(models.Module).filter(models.Module.user_id == current_user.id).all()


@app.delete("/modules/{module_id}")
def delete_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = _owned_module(db, module_id, current_user)
    db.delete(module)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Cours et quiz generes par IA
# ---------------------------------------------------------------------------
def _ai_http_error(error: Exception) -> HTTPException:
    if isinstance(error, AIConfigurationError):
        return HTTPException(503, "La generation IA n'est pas configuree sur le serveur.")
    return HTTPException(502, "La generation IA a echoue. Reessaie dans quelques instants.")


@app.post(
    "/modules/{module_id}/courses/generate",
    response_model=schemas.GeneratedCourseOut,
)
def generate_course_endpoint(
    module_id: int,
    req: schemas.CourseGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = _owned_module(db, module_id, current_user)

    try:
        generated = generate_course_ai(
            subject=req.subject,
            level=req.level,
            language=req.language,
            desired_length=req.desired_length,
            objectives=req.objectives,
            requested_chapters=req.chapters,
        )
        chapters = [
            schemas.CourseChapter.model_validate(chapter).model_dump()
            for chapter in generated.get("chapters", [])
        ]
        content = generated.get("content", "").strip()
        summary = generated.get("summary", "").strip()
        if not chapters or not content or not summary:
            raise ValueError("Contenu de cours incomplet")
    except (AIConfigurationError, AIGenerationError) as exc:
        raise _ai_http_error(exc) from exc
    except (AttributeError, TypeError, ValidationError, ValueError) as exc:
        raise HTTPException(502, "La reponse IA ne respecte pas le format attendu.") from exc

    course = models.GeneratedCourse(
        module_id=module.id,
        subject=req.subject,
        level=req.level,
        language=req.language,
        desired_length=req.desired_length,
        objectives=req.objectives,
        chapters=chapters,
        content=content,
        summary=summary,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


@app.get("/modules/{module_id}/courses", response_model=List[schemas.GeneratedCourseOut])
def list_generated_courses(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _owned_module(db, module_id, current_user)
    return (
        db.query(models.GeneratedCourse)
        .filter(models.GeneratedCourse.module_id == module_id)
        .order_by(models.GeneratedCourse.created_at.desc())
        .all()
    )


@app.get("/courses/{course_id}", response_model=schemas.GeneratedCourseOut)
def get_generated_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    return course


@app.patch("/courses/{course_id}", response_model=schemas.GeneratedCourseOut)
def update_generated_course(
    course_id: int,
    payload: schemas.CourseUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    course.subject = payload.subject.strip()
    if payload.content is not None:
        course.content = payload.content.strip()
    db.commit()
    db.refresh(course)
    return course


@app.post("/courses/{course_id}/move", response_model=schemas.GeneratedCourseOut)
def move_generated_course(
    course_id: int,
    payload: schemas.CourseMoveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    destination = _owned_module(db, payload.module_id, current_user)
    if destination.id != course.module_id:
        old_module_id = course.module_id
        course.module_id = destination.id
        db.query(models.QuizQuestion).filter(
            models.QuizQuestion.generated_course_id == course.id
        ).update({models.QuizQuestion.module_id: destination.id}, synchronize_session=False)
        db.query(models.QuizAttempt).filter(
            models.QuizAttempt.course_id == course.id
        ).update({models.QuizAttempt.module_id: destination.id}, synchronize_session=False)
        db.query(models.QuizProgress).filter(
            models.QuizProgress.course_id == course.id
        ).update({models.QuizProgress.module_id: destination.id}, synchronize_session=False)
        db.query(models.QuizQuestionExposure).filter(
            models.QuizQuestionExposure.course_id == course.id
        ).update({models.QuizQuestionExposure.module_id: destination.id}, synchronize_session=False)
        if old_module_id == destination.id:
            raise HTTPException(400, "Le cours est deja dans ce module")
    db.commit()
    db.refresh(course)
    return course


@app.delete("/courses/{course_id}")
def delete_generated_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    question_ids = [
        question_id
        for (question_id,) in db.query(models.QuizQuestion.id)
        .filter(models.QuizQuestion.generated_course_id == course.id)
        .all()
    ]
    if question_ids:
        db.query(models.QuizQuestionExposure).filter(
            models.QuizQuestionExposure.question_id.in_(question_ids)
        ).delete(synchronize_session=False)
    db.query(models.QuizQuestionExposure).filter(
        models.QuizQuestionExposure.course_id == course.id
    ).delete(synchronize_session=False)
    db.query(models.QuizProgress).filter(
        models.QuizProgress.course_id == course.id
    ).delete(synchronize_session=False)
    db.query(models.NotionStatus).filter(
        models.NotionStatus.course_id == course.id
    ).delete(synchronize_session=False)
    db.query(models.QuizAttempt).filter(
        models.QuizAttempt.course_id == course.id
    ).delete(synchronize_session=False)
    db.query(models.QuizQuestion).filter(
        models.QuizQuestion.generated_course_id == course.id
    ).delete(synchronize_session=False)
    db.delete(course)
    db.commit()
    return {"ok": True}


@app.post(
    "/courses/{course_id}/quiz/generate",
    response_model=List[schemas.QuestionOut],
)
def generate_quiz_endpoint(
    course_id: int,
    req: schemas.QuizGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    avoided_questions = [
        question
        for (question,) in db.query(models.QuizQuestion.question)
        .join(
            models.QuizQuestionExposure,
            models.QuizQuestionExposure.question_id == models.QuizQuestion.id,
        )
        .filter(
            models.QuizQuestionExposure.user_id == current_user.id,
            models.QuizQuestionExposure.course_id == course.id,
            models.QuizQuestionExposure.level == req.level,
        )
        .all()
    ]
    review_notions = [
        {
            "notion_key": status.notion_key,
            "notion_label": status.notion_label,
            "correct_answer": status.correct_answer,
        }
        for status in _review_statuses(db, current_user.id, course.id, limit=2)
    ]

    try:
        generated_questions = generate_quiz_ai(
            course_content=course.content,
            language=course.language,
            question_count=req.question_count,
            difficulty=req.difficulty,
            level=req.level,
            avoided_questions=avoided_questions,
            review_notions=review_notions,
        )
        questions = [
            schemas.GeneratedQuizQuestion.model_validate(question)
            for question in generated_questions
        ]
        if len(questions) != req.question_count:
            raise ValueError("Nombre de questions incorrect")
        keys = [_question_key(question.question) for question in questions]
        for question in questions:
            question.notion_key = _normalize_notion_key(question.notion_key, question.question)
        if len(keys) != len(set(keys)):
            raise ValueError("Questions dupliquees")
        if set(keys) & {_question_key(question) for question in avoided_questions}:
            raise ValueError("Question deja posee a cet utilisateur")
    except (AIConfigurationError, AIGenerationError) as exc:
        raise _ai_http_error(exc) from exc
    except (TypeError, ValidationError, ValueError) as exc:
        raise HTTPException(502, "La reponse IA ne respecte pas le format attendu.") from exc

    records = [
        models.QuizQuestion(
            module_id=course.module_id,
            generated_course_id=course.id,
            question=question.question,
            choices=question.choices,
            correct_index=question.correct_index,
            explanation=question.explanation,
            difficulty=req.difficulty,
            level=req.level,
            notion_key=question.notion_key,
        )
        for question in questions
    ]
    db.add_all(records)
    db.commit()
    for record in records:
        db.refresh(record)
    return records


# ---------------------------------------------------------------------------
# Quiz diagnostic
# ---------------------------------------------------------------------------
@app.get("/modules/{module_id}/quiz/levels", response_model=schemas.QuizLevelsOut)
def quiz_levels(
    module_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    if course.module_id != module_id:
        raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
    progress = _progress_for_course(db, current_user.id, course)
    attempts = (
        db.query(models.QuizAttempt)
        .filter(
            models.QuizAttempt.module_id == module_id,
            models.QuizAttempt.course_id == course.id,
            models.QuizAttempt.user_id == current_user.id,
            models.QuizAttempt.level.is_not(None),
        )
        .all()
    )
    best = {}
    for attempt in attempts:
        current = best.get(attempt.level)
        if current is None or attempt.score > current.score:
            best[attempt.level] = attempt
    return schemas.QuizLevelsOut(
        module_id=module_id,
        course_id=course.id,
        max_unlocked_level=progress.max_unlocked_level,
        levels=[
            schemas.QuizLevelOut(
                level=level,
                unlocked=level <= progress.max_unlocked_level,
                current=level == progress.max_unlocked_level,
                best_score=best[level].score if level in best else None,
                best_correct=best[level].correct_count if level in best else None,
                total_questions=best[level].total_questions if level in best else None,
                passed=any(
                    attempt.level == level and bool(attempt.passed) for attempt in attempts
                ),
            )
            for level in range(1, QUIZ_LEVEL_COUNT + 1)
        ],
    )


@app.post(
    "/modules/{module_id}/quiz/levels/{level}/start",
    response_model=schemas.QuizLevelSessionOut,
)
def start_quiz_level(
    module_id: int,
    level: int,
    req: schemas.QuizLevelStartRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not req.course_id:
        raise HTTPException(400, "Selectionne un cours pour lancer un niveau.")
    course = _owned_course(db, req.course_id, current_user)
    if course.module_id != module_id:
        raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
    _require_unlocked_level(db, course, level, current_user)
    shown_ids = _shown_question_ids(db, current_user.id, course.id, level)
    questions = (
        db.query(models.QuizQuestion)
        .filter(
            models.QuizQuestion.generated_course_id == course.id,
            models.QuizQuestion.level == level,
            ~models.QuizQuestion.id.in_(shown_ids or {-1}),
        )
        .limit(QUIZ_QUESTIONS_PER_LEVEL)
        .all()
    )
    if len(questions) < QUIZ_QUESTIONS_PER_LEVEL:
        questions = _generate_level_questions(db, course, level, current_user)

    for question in questions:
        db.add(
            models.QuizQuestionExposure(
                user_id=current_user.id,
                module_id=module_id,
                course_id=course.id,
                level=level,
                question_id=question.id,
            )
        )
    db.commit()
    return schemas.QuizLevelSessionOut(module_id=module_id, course_id=course.id, level=level, questions=questions)


@app.post("/modules/{module_id}/quiz/submit", response_model=schemas.QuizResult)
def submit_quiz(
    module_id: int,
    submission: schemas.QuizSubmit,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _owned_module(db, module_id, current_user)
    course = None

    if submission.level is not None:
        if not submission.course_id:
            raise HTTPException(400, "Un cours est requis pour un quiz par niveaux.")
        course = _owned_course(db, submission.course_id, current_user)
        if course.module_id != module_id:
            raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
        _require_unlocked_level(db, course, submission.level, current_user)

    question_query = db.query(models.QuizQuestion).filter(
        models.QuizQuestion.module_id == module_id
    )
    if submission.level is not None:
        question_query = question_query.filter(
            models.QuizQuestion.level == submission.level
        )
        question_query = question_query.filter(
            models.QuizQuestion.generated_course_id == course.id
        )
    questions = {
        q.id: q
        for q in question_query.all()
    }
    if not questions:
        raise HTTPException(400, "Aucune question pour ce module")

    submitted_ids = {answer.question_id for answer in submission.answers}
    unknown_ids = submitted_ids - set(questions)
    if unknown_ids:
        raise HTTPException(400, "Une ou plusieurs questions ne font pas partie de ce module")
    missing_ids = set(questions) - submitted_ids
    if submission.level is None and missing_ids:
        raise HTTPException(400, "Toutes les questions du quiz doivent recevoir une reponse")
    if submission.level is not None:
        shown_ids = _shown_question_ids(db, current_user.id, course.id, submission.level)
        if len(submission.answers) != QUIZ_QUESTIONS_PER_LEVEL or submitted_ids - shown_ids:
            raise HTTPException(400, "Les reponses ne correspondent pas a une session de niveau valide.")

    results = []
    correct = 0
    consolidated_count = 0
    for answer in submission.answers:
        question = questions[answer.question_id]
        if answer.selected_index >= len(question.choices):
            raise HTTPException(400, "Un index de reponse est hors limites")
        is_correct = answer.selected_index == question.correct_index
        correct += int(is_correct)
        correct_answer = question.choices[question.correct_index]
        explanation = question.explanation or f"La bonne reponse est : {correct_answer}."
        if course:
            consolidated_count += int(
                _update_notion_status(
                    db,
                    current_user.id,
                    course,
                    question,
                    is_correct,
                    correct_answer,
                    explanation,
                )
            )
        results.append(
            {
                "question_id": question.id,
                "question": question.question,
                "selected_index": answer.selected_index,
                "selected_answer": question.choices[answer.selected_index],
                "is_correct": is_correct,
                "correct_answer": correct_answer,
                "explanation": explanation,
                "notion_key": question.notion_key,
            }
        )

    total = len(questions)
    if submission.level is not None:
        total = QUIZ_QUESTIONS_PER_LEVEL
    score = round(100 * correct / total, 2)
    passed = score >= QUIZ_PASS_SCORE if submission.level is not None else None
    next_level_unlocked = None
    if submission.level is not None:
        progress = _progress_for_course(db, current_user.id, course)
        if passed and submission.level < QUIZ_LEVEL_COUNT:
            progress.max_unlocked_level = max(
                progress.max_unlocked_level, submission.level + 1
            )
            next_level_unlocked = True
        else:
            next_level_unlocked = submission.level < progress.max_unlocked_level

    attempt = models.QuizAttempt(
        module_id=module_id,
        user_id=current_user.id,
        score=score,
        correct_count=correct,
        total_questions=total,
        results=results,
        level=submission.level,
        passed=int(passed) if passed is not None else None,
        course_id=course.id if course else None,
    )
    db.add(attempt)
    db.commit()

    remaining_review_count = (
        len(_review_statuses(db, current_user.id, course.id)) if course else 0
    )

    if score >= 80:
        diagnostic = "Acquis — module maîtrisé"
    elif score >= 50:
        diagnostic = "En progrès — à consolider"
    else:
        diagnostic = "Faiblesse détectée — à prioriser"

    return schemas.QuizResult(
        module_id=module_id,
        score=score,
        correct=correct,
        incorrect=total - correct,
        total=total,
        diagnostic=diagnostic,
        results=results,
        level=submission.level,
        passed=passed,
        next_level_unlocked=next_level_unlocked,
        course_id=course.id if course else None,
        consolidated_count=consolidated_count,
        remaining_review_count=remaining_review_count,
    )


@app.get(
    "/modules/{module_id}/quiz/attempts",
    response_model=List[schemas.QuizAttemptOut],
)
def list_quiz_attempts(
    module_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    if course.module_id != module_id:
        raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
    return (
        db.query(models.QuizAttempt)
        .filter(
            models.QuizAttempt.module_id == module_id,
            models.QuizAttempt.course_id == course.id,
            models.QuizAttempt.user_id == current_user.id,
        )
        .order_by(models.QuizAttempt.date.desc())
        .all()
    )


@app.get("/modules/{module_id}/quiz/stats", response_model=schemas.QuizStatsOut)
def quiz_stats(
    module_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    if course.module_id != module_id:
        raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
    attempts = (
        db.query(models.QuizAttempt)
        .filter(
            models.QuizAttempt.module_id == module_id,
            models.QuizAttempt.course_id == course.id,
            models.QuizAttempt.user_id == current_user.id,
        )
        .all()
    )
    scores = [attempt.score for attempt in attempts]
    progress = _progress_for_course(db, current_user.id, course)
    level_attempts = [attempt for attempt in attempts if attempt.level is not None]
    best_by_level = []
    for level in sorted({attempt.level for attempt in level_attempts}):
        entries = [attempt for attempt in level_attempts if attempt.level == level]
        best = max(entries, key=lambda attempt: attempt.score)
        best_by_level.append(
            schemas.LevelBestOut(
                level=level,
                best_score=best.score,
                best_correct=best.correct_count,
                total_questions=best.total_questions,
                passed=any(bool(attempt.passed) for attempt in entries),
            )
        )
    return schemas.QuizStatsOut(
        module_id=module_id,
        user_id=current_user.id,
        attempt_count=len(attempts),
        average_score=round(sum(scores) / len(scores), 2) if scores else None,
        best_score=max(scores) if scores else None,
        course_id=course.id,
        level_reached=progress.max_unlocked_level,
        best_by_level=best_by_level,
    )


@app.get("/modules/{module_id}/quiz/review", response_model=List[schemas.ReviewItemOut])
def quiz_review(
    module_id: int,
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = _owned_course(db, course_id, current_user)
    if course.module_id != module_id:
        raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
    return [
        schemas.ReviewItemOut(
            question_id=status.id,
            notion=status.notion_label,
            mistake_count=status.review_count,
            correct_answer=status.correct_answer,
            explanation=status.explanation or "",
        )
        for status in _review_statuses(db, current_user.id, course.id)
    ]


# ---------------------------------------------------------------------------
# Génération du planning (règle heuristique "faiblesses d'abord")
# ---------------------------------------------------------------------------
def _module_avg_score(db: Session, module_id: int) -> Optional[float]:
    attempts = (
        db.query(models.QuizAttempt)
        .filter(models.QuizAttempt.module_id == module_id)
        .all()
    )
    if not attempts:
        return None
    return sum(a.score for a in attempts) / len(attempts)


def _course_avg_score(db: Session, course_id: int) -> Optional[float]:
    scores = [
        attempt.score
        for attempt in db.query(models.QuizAttempt)
        .filter(models.QuizAttempt.course_id == course_id)
        .all()
    ]
    return sum(scores) / len(scores) if scores else None


@app.post("/plans/generate", response_model=schemas.PlanOut)
def generate_plan_endpoint(
    req: schemas.PlanGenerateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    modules = db.query(models.Module).filter(models.Module.user_id == current_user.id).all()
    if not modules:
        raise HTTPException(400, "Aucun module pour cet utilisateur")

    modules_data = [
        {
            "id": m.id,
            "name": m.name,
            "weekly_objective_hours": m.weekly_objective_hours,
            "avg_score": _module_avg_score(db, m.id),
        }
        for m in modules
    ]

    entries = generate_plan(modules_data, req.total_hours_per_week, req.days_per_week)

    plan = models.Plan(
        user_id=current_user.id,
        total_hours_per_week=req.total_hours_per_week,
        days_per_week=req.days_per_week,
        entries=entries,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


@app.get("/plans/latest", response_model=schemas.PlanOut)
@app.get("/plans/{user_id}/latest", response_model=schemas.PlanOut, deprecated=True)
def latest_plan(
    user_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if user_id is not None and user_id != current_user.id:
        raise HTTPException(403, "Acces interdit a ce planning")
    plan = (
        db.query(models.Plan)
        .filter(models.Plan.user_id == current_user.id)
        .order_by(models.Plan.created_at.desc())
        .first()
    )
    if not plan:
        raise HTTPException(404, "Aucun planning généré pour cet utilisateur")
    return plan


# ---------------------------------------------------------------------------
# Notifications (simulées)
# ---------------------------------------------------------------------------
def _overdue_revision_modules(db: Session, user_id: int) -> list[str]:
    overdue = []
    for module in db.query(models.Module).filter(models.Module.user_id == user_id).all():
        attempts = db.query(models.QuizAttempt).filter(
            models.QuizAttempt.module_id == module.id,
            models.QuizAttempt.user_id == user_id,
        ).all()
        result = compute_retention([{"date": attempt.date, "score": attempt.score} for attempt in attempts])
        if result["next_review"] and result["next_review"] < date.today():
            overdue.append(module.name)
    return overdue


def _retention_payload(module: models.Module, attempts: list[models.QuizAttempt]) -> schemas.RetentionOut:
    """Transforme l'historique SQLite en reponse API sans exposer les quiz."""
    history = [
        schemas.RetentionHistoryItem(date=attempt.date, score=attempt.score)
        for attempt in sorted(attempts, key=lambda item: item.date)
    ]
    result = compute_retention([{"date": item.date, "score": item.score} for item in history])
    return schemas.RetentionOut(
        module_id=module.id,
        module_name=module.name,
        history=history,
        last_score=result["last_score"],
        interval_days=result["interval_days"],
        next_review=result["next_review"],
        ef=result["ef"],
        reps=result["reps"],
        days_since=result["days_since"],
        retention=result["retention"],
        overdue_days=result["overdue_days"],
    )


def _create_due_retention_notifications(
    db: Session, current_user: models.User
) -> list[models.Notification]:
    """Cree au plus un rappel quotidien par module lorsque la retention est sous 90 %."""
    created = []
    today_start = datetime.datetime.combine(date.today(), datetime.time.min)
    modules = db.query(models.Module).filter(models.Module.user_id == current_user.id).all()
    for module in modules:
        attempts = (
            db.query(models.QuizAttempt)
            .filter(
                models.QuizAttempt.module_id == module.id,
                models.QuizAttempt.user_id == current_user.id,
            )
            .all()
        )
        retention = compute_retention([{"date": item.date, "score": item.score} for item in attempts])
        if retention["retention"] is None or retention["retention"] >= 0.9:
            continue
        subject = f"A reviser : {module.name}"
        already_sent = (
            db.query(models.Notification)
            .filter(
                models.Notification.user_id == current_user.id,
                models.Notification.subject == subject,
                models.Notification.sent_at >= today_start,
            )
            .first()
        )
        if already_sent:
            continue
        notification = models.Notification(
            user_id=current_user.id,
            subject=subject,
            body=(
                f"Votre retention estimee pour {module.name} est de "
                f"{round(retention['retention'] * 100)} %. Une courte revision est recommandee."
            ),
            simulated="true",
        )
        db.add(notification)
        created.append(notification)
    if created:
        db.commit()
        for notification in created:
            db.refresh(notification)
    return created


def _send_smtp_email(recipient: str, subject: str, body: str) -> bool:
    """Envoie un e-mail si, et seulement si, SMTP est configure cote serveur."""
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USERNAME")
    if not host or not sender:
        return False
    try:
        port = int(os.getenv("SMTP_PORT", "587"))
    except ValueError as exc:
        raise HTTPException(500, "SMTP_PORT doit etre un entier valide.") from exc

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    try:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if os.getenv("SMTP_USE_TLS", "true").lower() != "false":
                smtp.starttls(context=ssl.create_default_context())
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise HTTPException(502, "L'e-mail n'a pas pu etre envoye. Verifie la configuration SMTP.") from exc
    return True


@app.post("/notifications/send", response_model=schemas.NotificationOut)
def send_notification(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    user = current_user

    plan = (
        db.query(models.Plan)
        .filter(models.Plan.user_id == current_user.id)
        .order_by(models.Plan.created_at.desc())
        .first()
    )
    if plan and plan.entries:
        lines = "\n".join(
            f"- {e['day']}: {e['module_name']} ({e['hours']}h) [{e['priority']}]"
            for e in plan.entries
        )
        body = f"Bonjour {user.name},\n\nVoici votre planning de révision de la semaine :\n{lines}\n\nBon courage !"
    else:
        body = f"Bonjour {user.name},\n\nAucun planning n'a encore été généré. Rendez-vous dans l'application pour en créer un."

    body = body.removesuffix("\n\nBon courage !")
    overdue = _overdue_revision_modules(db, current_user.id)
    if overdue:
        body += "\n\nRevisions a rattraper :\n" + "\n".join(f"- {name}" for name in overdue)
    body += "\n\nBon courage !" if not body.endswith("Bon courage !") else ""
    subject = "Votre planning de revision"
    delivered = _send_smtp_email(user.email, subject, body)

    notif = models.Notification(
        user_id=current_user.id,
        subject=subject,
        body=body,
        simulated="false" if delivered else "true",
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


@app.get("/notifications", response_model=List[schemas.NotificationOut])
def list_notifications(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.sent_at.desc())
        .all()
    )


@app.post("/retention/notifications/refresh", response_model=List[schemas.NotificationOut])
def refresh_retention_notifications(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    """Evalue les rappels au moment ou l'utilisateur consulte sa retention."""
    return _create_due_retention_notifications(db, current_user)


# ---------------------------------------------------------------------------
# BONUS — Recommandation de ressources (IA + secours par règles)
# ---------------------------------------------------------------------------
@app.get("/modules/{module_id}/resources", response_model=List[schemas.ResourceOut])
def module_resources(
    module_id: int,
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = _owned_module(db, module_id, current_user)
    course = None
    if course_id is not None:
        course = _owned_course(db, course_id, current_user)
        if course.module_id != module.id:
            raise HTTPException(400, "Ce cours n'appartient pas au module selectionne.")
    resource_context = (
        f"{course.subject}\n{course.summary}" if course else module.course or ""
    )
    average_score = _course_avg_score(db, course.id) if course else _module_avg_score(db, module_id)

    # 1) Essai avec l'IA si une clé API est configurée
    if os.getenv("GEMINI_API_KEY"):
        try:
            return recommend_resources_ai(
                module.name, resource_context, average_score
            )
        except Exception as e:
            print("IA indisponible, utilisation des règles :", e)

    # 2) Secours : recommandation par mots-clés
    return recommend_resources(module.name, resource_context)


# ---------------------------------------------------------------------------
# BONUS — Courbe de rétention (spaced repetition light)
# ---------------------------------------------------------------------------
@app.get("/retention", response_model=List[schemas.RetentionOut])
def retention_history(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Historique de chaque module de l'utilisateur, trie chronologiquement."""
    modules = (
        db.query(models.Module)
        .filter(models.Module.user_id == current_user.id)
        .order_by(models.Module.name.asc())
        .all()
    )
    return [
        _retention_payload(
            module,
            db.query(models.QuizAttempt)
            .filter(
                models.QuizAttempt.module_id == module.id,
                models.QuizAttempt.user_id == current_user.id,
            )
            .all(),
        )
        for module in modules
    ]


@app.get("/modules/{module_id}/retention", response_model=schemas.RetentionOut)
def module_retention(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = _owned_module(db, module_id, current_user)

    attempts = (
        db.query(models.QuizAttempt)
        .filter(
            models.QuizAttempt.module_id == module_id,
            models.QuizAttempt.user_id == current_user.id,
        )
        .all()
    )
    return _retention_payload(module, attempts)


@app.get("/")
def root():
    return {"message": "Assistant de révisions personnalisé — API", "docs": "/docs"}
