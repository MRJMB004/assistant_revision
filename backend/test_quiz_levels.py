import os
import tempfile
import unittest
from unittest.mock import patch

database_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
database_file.close()
os.environ["DATABASE_URL"] = f"sqlite:///{database_file.name}"
os.environ["JWT_SECRET"] = "test-secret-for-course-levels"

import main
import models
import schemas
from database import Base, SessionLocal, engine
from fastapi import HTTPException


class CourseQuizTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        engine.dispose()
        os.unlink(database_file.name)

    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.user = models.User(name="Test", email="test@example.com", password_hash="hash")
        self.db.add(self.user); self.db.flush()
        self.module = models.Module(user_id=self.user.id, name="Electricite")
        self.destination = models.Module(user_id=self.user.id, name="Mecanique")
        self.db.add_all([self.module, self.destination]); self.db.flush()
        self.course_a = self._course("Cours A")
        self.course_b = self._course("Cours B")
        for course in (self.course_a, self.course_b):
            for index in range(5):
                self.db.add(models.QuizQuestion(module_id=self.module.id, generated_course_id=course.id, level=1, question=f"{course.subject} {index}", choices=["bonne", "fausse"], correct_index=0))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def _course(self, subject):
        course = models.GeneratedCourse(module_id=self.module.id, subject=subject, level="Debutant", language="fr", desired_length=300, objectives=["x"], chapters=[], content="contenu", summary="resume")
        self.db.add(course); self.db.flush()
        return course

    def _start(self, course):
        return main.start_quiz_level(self.module.id, 1, schemas.QuizLevelStartRequest(course_id=course.id), self.db, self.user)

    def _submit(self, course, correct):
        session = self._start(course)
        answers = [schemas.AnswerIn(question_id=q.id, selected_index=0 if index < correct else 1) for index, q in enumerate(session.questions)]
        return main.submit_quiz(self.module.id, schemas.QuizSubmit(course_id=course.id, level=1, answers=answers), self.db, self.user)

    def test_independent_progress_and_threshold(self):
        self.assertFalse(self._submit(self.course_a, 3).passed)
        with self.assertRaises(HTTPException): main._require_unlocked_level(self.db, self.course_a, 2, self.user)
        self.assertTrue(self._submit(self.course_b, 4).passed)
        self.assertEqual(main._require_unlocked_level(self.db, self.course_b, 2, self.user).max_unlocked_level, 2)
        with self.assertRaises(HTTPException): main._require_unlocked_level(self.db, self.course_a, 2, self.user)

    def test_move_keeps_progress(self):
        self._submit(self.course_a, 5)
        moved = main.move_generated_course(self.course_a.id, schemas.CourseMoveRequest(module_id=self.destination.id), self.db, self.user)
        self.assertEqual(moved.module_id, self.destination.id)
        self.assertEqual(main._require_unlocked_level(self.db, moved, 2, self.user).max_unlocked_level, 2)

    def test_delete_cascades_course_data(self):
        self._submit(self.course_a, 4)
        main.delete_generated_course(self.course_a.id, self.db, self.user)
        self.assertIsNone(self.db.get(models.GeneratedCourse, self.course_a.id))
        self.assertEqual(self.db.query(models.QuizQuestion).filter_by(generated_course_id=self.course_a.id).count(), 0)
        self.assertEqual(self.db.query(models.QuizAttempt).filter_by(course_id=self.course_a.id).count(), 0)
        self.assertEqual(self.db.query(models.QuizProgress).filter_by(course_id=self.course_a.id).count(), 0)

    def test_manual_route_removed_and_locked_level_forbidden(self):
        self.assertNotIn("/modules/{module_id}/questions", main.app.openapi()["paths"])
        with self.assertRaises(HTTPException) as error:
            main._require_unlocked_level(self.db, self.course_a, 2, self.user)
        self.assertEqual(error.exception.status_code, 403)

    def test_notion_counter_decreases_and_never_becomes_negative(self):
        question = self.db.query(models.QuizQuestion).filter_by(generated_course_id=self.course_a.id).first()
        question.notion_key = "loi-ohm"
        main._update_notion_status(self.db, self.user.id, self.course_a, question, False, "U = R x I", "Relation entre tension, resistance et intensite.")
        main._update_notion_status(self.db, self.user.id, self.course_a, question, True, "U = R x I", "Relation entre tension, resistance et intensite.")
        status = self.db.query(models.NotionStatus).filter_by(course_id=self.course_a.id, notion_key="loi-ohm").one()
        self.assertEqual(status.review_count, 0)
        self.assertEqual(main.quiz_review(self.module.id, self.course_a.id, self.db, self.user), [])
        main._update_notion_status(self.db, self.user.id, self.course_a, question, False, "U = R x I", "Relation entre tension, resistance et intensite.")
        main._update_notion_status(self.db, self.user.id, self.course_a, question, False, "U = R x I", "Relation entre tension, resistance et intensite.")
        main._update_notion_status(self.db, self.user.id, self.course_a, question, True, "U = R x I", "Relation entre tension, resistance et intensite.")
        self.assertEqual(status.review_count, 1)
        for _ in range(5):
            main._update_notion_status(self.db, self.user.id, self.course_a, question, False, "U = R x I", "Relation entre tension, resistance et intensite.")
        self.assertEqual(status.review_count, 3)
        main._update_notion_status(self.db, self.user.id, self.course_a, question, True, "U = R x I", "Relation entre tension, resistance et intensite.")
        main._update_notion_status(self.db, self.user.id, self.course_a, question, True, "U = R x I", "Relation entre tension, resistance et intensite.")
        main._update_notion_status(self.db, self.user.id, self.course_a, question, True, "U = R x I", "Relation entre tension, resistance et intensite.")
        self.assertEqual(status.review_count, 0)

    def test_questions_with_same_notion_share_one_counter_and_are_course_scoped(self):
        questions = self.db.query(models.QuizQuestion).filter_by(generated_course_id=self.course_a.id).limit(2).all()
        for question in questions:
            question.notion_key = "unite-resistance"
            main._update_notion_status(self.db, self.user.id, self.course_a, question, False, "ohm", "Unite SI de la resistance.")
        self.db.commit()
        self.assertEqual(self.db.query(models.NotionStatus).filter_by(course_id=self.course_a.id, notion_key="unite-resistance").one().review_count, 2)
        self.assertEqual(main.quiz_review(self.module.id, self.course_a.id, self.db, self.user)[0].mistake_count, 2)
        self.assertEqual(main.quiz_review(self.module.id, self.course_b.id, self.db, self.user), [])

    def test_next_generation_receives_at_most_two_recall_notions(self):
        for index in range(3):
            self.db.add(models.NotionStatus(user_id=self.user.id, course_id=self.course_a.id, notion_key=f"notion-{index}", notion_label=f"Notion {index}", correct_answer="Bonne", explanation="Explication", review_count=index + 1))
        self.db.commit()
        captured = {}

        def generated_quiz(**kwargs):
            captured["review_notions"] = kwargs["review_notions"]
            recalls = kwargs["review_notions"]
            return [
                {"question": f"Question {index}", "choices": ["Bonne", "A", "B", "C"], "correct_index": 0, "explanation": "Explication", "notion_key": recalls[index]["notion_key"] if index < len(recalls) else f"nouvelle-notion-{index}"}
                for index in range(5)
            ]

        with patch("main.generate_quiz_ai", side_effect=generated_quiz):
            main._generate_level_questions(self.db, self.course_a, 2, self.user)
        self.assertEqual(len(captured["review_notions"]), 2)

    def test_migration_initializes_historical_balance(self):
        question = self.db.query(models.QuizQuestion).filter_by(generated_course_id=self.course_a.id).first()
        question.notion_key = None
        self.db.add(models.QuizAttempt(module_id=self.module.id, user_id=self.user.id, course_id=self.course_a.id, score=0, results=[{"question_id": question.id, "question": question.question, "is_correct": False, "correct_answer": "bonne", "explanation": "x"}]))
        self.db.add(models.QuizAttempt(module_id=self.module.id, user_id=self.user.id, course_id=self.course_a.id, score=100, results=[{"question_id": question.id, "question": question.question, "is_correct": True, "correct_answer": "bonne", "explanation": "x"}]))
        self.db.commit()
        self.db.query(models.NotionStatus).delete(); self.db.commit()
        main._migrate_notion_tracking()
        status = self.db.query(models.NotionStatus).filter_by(course_id=self.course_a.id).one()
        self.assertEqual(status.review_count, 0)

    def test_migration_uses_the_question_course_not_a_legacy_attempt_course(self):
        question = self.db.query(models.QuizQuestion).filter_by(generated_course_id=self.course_a.id).first()
        self.db.add(models.QuizAttempt(module_id=self.module.id, user_id=self.user.id, course_id=self.course_b.id, score=0, results=[{"question_id": question.id, "question": question.question, "is_correct": False, "correct_answer": "bonne", "explanation": "x"}]))
        self.db.commit()
        self.db.query(models.NotionStatus).delete(); self.db.commit()
        main._migrate_notion_tracking()
        self.assertEqual(self.db.query(models.NotionStatus).filter_by(course_id=self.course_a.id).count(), 1)
        self.assertEqual(self.db.query(models.NotionStatus).filter_by(course_id=self.course_b.id).count(), 0)

    def test_migration_merges_nearly_identical_legacy_questions(self):
        first, second = self.db.query(models.QuizQuestion).filter_by(generated_course_id=self.course_a.id).limit(2).all()
        first.question = "Quelle est l'unite de la resistance ?"; first.notion_key = None
        second.question = "Quelle unite mesure la resistance electrique ?"; second.notion_key = None
        self.db.add_all([
            models.QuizAttempt(module_id=self.module.id, user_id=self.user.id, course_id=self.course_a.id, score=0, results=[{"question_id": first.id, "question": first.question, "is_correct": False, "correct_answer": "ohm", "explanation": "x"}]),
            models.QuizAttempt(module_id=self.module.id, user_id=self.user.id, course_id=self.course_a.id, score=0, results=[{"question_id": second.id, "question": second.question, "is_correct": False, "correct_answer": "ohm", "explanation": "x"}]),
        ])
        self.db.commit(); self.db.query(models.NotionStatus).delete(); self.db.commit()
        main._migrate_notion_tracking()
        statuses = self.db.query(models.NotionStatus).filter_by(course_id=self.course_a.id).all()
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0].review_count, 2)


if __name__ == "__main__":
    unittest.main()
