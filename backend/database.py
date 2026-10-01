"""
Configuration de la base de données SQLite via SQLAlchemy.
"""
import os

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./revisions.db")

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_schema():
    """Ajoute les colonnes IA absentes sur une base SQLite existante."""
    user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    with engine.begin() as connection:
        if "password_hash" not in user_columns:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR"))

    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("quiz_questions")
    }
    migrations = {
        "generated_course_id": "INTEGER",
        "explanation": "TEXT",
        "difficulty": "VARCHAR",
        "level": "INTEGER NOT NULL DEFAULT 1",
        "notion_key": "VARCHAR",
    }
    with engine.begin() as connection:
        for name, sql_type in migrations.items():
            if name not in existing_columns:
                connection.execute(
                    text(f"ALTER TABLE quiz_questions ADD COLUMN {name} {sql_type}")
                )

    attempt_columns = {
        column["name"] for column in inspect(engine).get_columns("quiz_attempts")
    }
    attempt_migrations = {
        "correct_count": "INTEGER",
        "total_questions": "INTEGER",
        "results": "JSON",
        "level": "INTEGER",
        "passed": "INTEGER",
    }
    with engine.begin() as connection:
        for name, sql_type in attempt_migrations.items():
            if name not in attempt_columns:
                connection.execute(
                    text(f"ALTER TABLE quiz_attempts ADD COLUMN {name} {sql_type}")
                )
        if "course_id" not in attempt_columns:
            connection.execute(text("ALTER TABLE quiz_attempts ADD COLUMN course_id INTEGER"))
        connection.execute(
            text(
                "UPDATE quiz_attempts SET course_id = ("
                "SELECT id FROM generated_courses WHERE generated_courses.module_id = quiz_attempts.module_id "
                "ORDER BY created_at DESC, id DESC LIMIT 1) WHERE course_id IS NULL"
            )
        )

    progress_columns = {column["name"] for column in inspect(engine).get_columns("quiz_progress")}
    exposure_columns = {column["name"] for column in inspect(engine).get_columns("quiz_question_exposures")}
    with engine.begin() as connection:
        if "course_id" not in progress_columns:
            connection.execute(text("ALTER TABLE quiz_progress RENAME TO quiz_progress_legacy"))
            connection.execute(text("""
                CREATE TABLE quiz_progress (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    module_id INTEGER NOT NULL,
                    course_id INTEGER,
                    max_unlocked_level INTEGER NOT NULL DEFAULT 1,
                    UNIQUE(user_id, course_id)
                )
            """))
            connection.execute(text("""
                INSERT INTO quiz_progress (id, user_id, module_id, course_id, max_unlocked_level)
                SELECT p.id, p.user_id, p.module_id,
                    (SELECT id FROM generated_courses WHERE module_id = p.module_id ORDER BY created_at DESC, id DESC LIMIT 1),
                    p.max_unlocked_level
                FROM quiz_progress_legacy p
            """))
            connection.execute(text("DROP TABLE quiz_progress_legacy"))
        if "course_id" not in exposure_columns:
            connection.execute(text("ALTER TABLE quiz_question_exposures RENAME TO quiz_question_exposures_legacy"))
            connection.execute(text("""
                CREATE TABLE quiz_question_exposures (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    module_id INTEGER NOT NULL,
                    course_id INTEGER,
                    level INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    shown_at DATETIME,
                    UNIQUE(user_id, course_id, level, question_id)
                )
            """))
            connection.execute(text("""
                INSERT INTO quiz_question_exposures (id, user_id, module_id, course_id, level, question_id, shown_at)
                SELECT e.id, e.user_id, e.module_id,
                    COALESCE(q.generated_course_id, (SELECT id FROM generated_courses WHERE module_id = e.module_id ORDER BY created_at DESC, id DESC LIMIT 1)),
                    e.level, e.question_id, e.shown_at
                FROM quiz_question_exposures_legacy e
                LEFT JOIN quiz_questions q ON q.id = e.question_id
            """))
            connection.execute(text("DROP TABLE quiz_question_exposures_legacy"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_quiz_attempts_course_id ON quiz_attempts (course_id)"))
        # Le panneau de consolidation reste volontairement compact.
        connection.execute(text("UPDATE notion_status SET review_count = 3 WHERE review_count > 3"))
