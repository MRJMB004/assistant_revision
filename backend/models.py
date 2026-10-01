"""
Modèles de données : User, Module, QuizQuestion, QuizAttempt, Plan, Notification.
"""
import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    Text,
    JSON,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)

    modules = relationship("Module", back_populates="owner", cascade="all, delete")


class Module(Base):
    __tablename__ = "modules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    course = Column(String, nullable=True)
    weekly_objective_hours = Column(Float, default=2.0)

    owner = relationship("User", back_populates="modules")
    questions = relationship(
        "QuizQuestion", back_populates="module", cascade="all, delete"
    )
    attempts = relationship(
        "QuizAttempt", back_populates="module", cascade="all, delete"
    )
    generated_courses = relationship(
        "GeneratedCourse", back_populates="module", cascade="all, delete"
    )


class GeneratedCourse(Base):
    __tablename__ = "generated_courses"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False, index=True)
    subject = Column(String, nullable=False)
    level = Column(String, nullable=False)
    language = Column(String, nullable=False)
    desired_length = Column(Integer, nullable=False)
    objectives = Column(JSON, nullable=False)
    chapters = Column(JSON, nullable=False)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    ai_generated = Column(String, default="true", nullable=False)

    module = relationship("Module", back_populates="generated_courses")
    questions = relationship("QuizQuestion", back_populates="generated_course")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    question = Column(Text, nullable=False)
    choices = Column(JSON, nullable=False)  # liste de chaînes
    correct_index = Column(Integer, nullable=False)
    generated_course_id = Column(
        Integer, ForeignKey("generated_courses.id"), nullable=True, index=True
    )
    explanation = Column(Text, nullable=True)
    difficulty = Column(String, nullable=True)
    level = Column(Integer, nullable=False, default=1, index=True)
    notion_key = Column(String, nullable=True, index=True)

    module = relationship("Module", back_populates="questions")
    generated_course = relationship("GeneratedCourse", back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(Integer, primary_key=True, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(DateTime, default=datetime.datetime.utcnow)
    score = Column(Float, nullable=False)  # 0-100
    correct_count = Column(Integer, nullable=True)
    total_questions = Column(Integer, nullable=True)
    results = Column(JSON, nullable=True)
    level = Column(Integer, nullable=True, index=True)
    passed = Column(Integer, nullable=True)
    course_id = Column(Integer, ForeignKey("generated_courses.id"), nullable=True, index=True)

    module = relationship("Module", back_populates="attempts")


class QuizProgress(Base):
    __tablename__ = "quiz_progress"
    __table_args__ = (UniqueConstraint("user_id", "course_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("generated_courses.id"), nullable=True, index=True)
    max_unlocked_level = Column(Integer, nullable=False, default=1)


class QuizQuestionExposure(Base):
    __tablename__ = "quiz_question_exposures"
    __table_args__ = (UniqueConstraint("user_id", "course_id", "level", "question_id"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    module_id = Column(Integer, ForeignKey("modules.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("generated_courses.id"), nullable=True, index=True)
    level = Column(Integer, nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("quiz_questions.id"), nullable=False)
    shown_at = Column(DateTime, default=datetime.datetime.utcnow)


class NotionStatus(Base):
    __tablename__ = "notion_status"
    __table_args__ = (UniqueConstraint("user_id", "course_id", "notion_key"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("generated_courses.id"), nullable=False, index=True)
    notion_key = Column(String, nullable=False, index=True)
    notion_label = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    review_count = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class Plan(Base):
    __tablename__ = "plans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    total_hours_per_week = Column(Float, nullable=False)
    days_per_week = Column(Integer, nullable=False)
    entries = Column(JSON, nullable=False)  # planning généré (liste de créneaux)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at = Column(DateTime, default=datetime.datetime.utcnow)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    simulated = Column(String, default="true")  # "true" ou "false"
