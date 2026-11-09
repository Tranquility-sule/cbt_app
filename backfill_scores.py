"""
One-time backfill for attempts that were submitted before raw_score /
total_marks_snapshot existed. Safe to run repeatedly.

Usage:
    python backfill_scores.py
"""
from app import create_app
from models import db, ExamAttempt
from grading import compute_score


def main():
    app = create_app()
    with app.app_context():
        candidates = ExamAttempt.query.filter(
            ExamAttempt.status != "in_progress",
            ExamAttempt.raw_score.is_(None),
        ).all()

        if not candidates:
            print("Nothing to backfill — every submitted attempt already has a raw score.")
            return

        updated = []
        for attempt in candidates:
            earned, total, percentage = compute_score(attempt)
            attempt.raw_score = earned
            attempt.total_marks_snapshot = total
            if attempt.score is None:
                attempt.score = percentage
            updated.append((attempt.user.reg_no, attempt.exam.title, earned, total))

        db.session.commit()

        print(f"Backfilled {len(updated)} attempt(s):")
        for reg_no, exam_title, earned, total in updated:
            print(f"  {reg_no} — {exam_title}: {earned:g} / {total:g}")


if __name__ == "__main__":
    main()
