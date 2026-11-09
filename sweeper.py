"""
Belt-and-braces auto-submit sweep.

The timer is already enforced on every page load and every answer-save
call (see routes/exam.py: take_exam, save_answer, heartbeat). But if a
student's device loses power or network entirely and never sends another
request, their attempt would stay "in_progress" forever without this.
"""
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

from models import db, ExamAttempt
from grading import compute_score


def sweep_expired_attempts(app):
    with app.app_context():
        in_progress = ExamAttempt.query.filter_by(status="in_progress").all()
        now = datetime.utcnow()
        closed = 0
        for attempt in in_progress:
            if now >= attempt.deadline():
                attempt.status = "auto_submitted"
                attempt.submitted_at = now
                earned, total, percentage = compute_score(attempt)
                attempt.raw_score = earned
                attempt.total_marks_snapshot = total
                attempt.score = percentage
                closed += 1
        if closed:
            db.session.commit()
            app.logger.info(f"Auto-submitted {closed} expired exam attempt(s).")


def start_sweeper(app):
    scheduler = BackgroundScheduler(daemon=True)
    interval = app.config.get("AUTOSUBMIT_SWEEP_SECONDS", 30)
    scheduler.add_job(
        func=lambda: sweep_expired_attempts(app),
        trigger="interval",
        seconds=interval,
        id="expired_attempt_sweeper",
        replace_existing=True,
    )
    scheduler.start()
    return scheduler
