import random as _random
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, jsonify, request
from flask_login import login_required, current_user

from models import db, Exam, ExamAttempt, Answer, Question, Attendance, ExamViolation
from shuffle import ordered_questions, ordered_options
from grading import compute_score

exam_bp = Blueprint("exam", __name__)


@exam_bp.route("/exams")
@login_required
def list_exams():
    all_exams = Exam.query.order_by(Exam.created_at.desc()).all()

    # A department-restricted exam is invisible to students outside that
    # department — not just blocked, but not shown at all.
    student_dept = (current_user.department or "").strip().lower()
    exams = [
        e for e in all_exams
        if not e.restricted_department or e.restricted_department.strip().lower() == student_dept
    ]

    exam_status = {}
    for exam in exams:
        attempt = exam.attempt_for(current_user.id)
        if attempt and attempt.status != "in_progress":
            exam_status[exam.id] = "done"
        elif attempt and attempt.status == "in_progress":
            exam_status[exam.id] = "resume"
        else:
            exam_status[exam.id] = "active"
    return render_template("exam_list.html", exams=exams, exam_status=exam_status)


@exam_bp.route("/exams/<int:exam_id>/start", methods=["POST"])
@login_required
def start_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)

    if not exam.is_open_for(current_user):
        if exam.restricted_department and not exam.locked:
            flash(f"This exam is restricted to {exam.restricted_department} students.", "error")
        else:
            flash("This exam is not currently open.", "error")
        return redirect(url_for("exam.list_exams"))

    # attempt_for() returns None if the student's most recent attempt was
    # superseded by a granted retake or deleted outright — either way that
    # correctly lets a fresh attempt begin without touching old history.
    attempt = exam.attempt_for(current_user.id)

    if attempt and attempt.status != "in_progress":
        flash("You have already submitted this exam.", "info")
        return redirect(url_for("exam.results", attempt_id=attempt.id))

    if not attempt:
        attempt = ExamAttempt(
            user_id=current_user.id,
            exam_id=exam.id,
            started_at=datetime.utcnow(),
            shuffle_seed=_random.randint(1, 2_000_000_000),
        )
        db.session.add(attempt)

        already_marked = Attendance.query.filter_by(
            user_id=current_user.id, exam_id=exam.id
        ).first()
        if not already_marked:
            db.session.add(Attendance(
                user_id=current_user.id,
                exam_id=exam.id,
                reg_no=current_user.reg_no,
                name=current_user.name,
                checked_in_at=datetime.utcnow(),
            ))

        db.session.commit()

    return redirect(url_for("exam.take_exam", attempt_id=attempt.id))


@exam_bp.route("/attempt/<int:attempt_id>")
@login_required
def take_exam(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        flash("Not authorized.", "error")
        return redirect(url_for("exam.list_exams"))

    if attempt.status == "in_progress" and attempt.is_expired():
        _finalize_attempt(attempt, status="auto_submitted")
        db.session.commit()

    if attempt.status != "in_progress":
        return redirect(url_for("exam.results", attempt_id=attempt.id))

    exam = attempt.exam
    questions = ordered_questions(exam.questions, attempt.shuffle_seed, exam.shuffle_questions)

    existing_answers = {a.question_id: a.selected_option_id for a in attempt.answers}

    question_payload = []
    for q in questions:
        opts = ordered_options(q.options, attempt.shuffle_seed, q.id, exam.shuffle_options)
        question_payload.append({
            "id": q.id,
            "text": q.text,
            "image_path": q.image_path,
            "options": [{"id": o.id, "text": o.text} for o in opts],
            "selected_option_id": existing_answers.get(q.id),
        })

    return render_template(
        "take_exam.html",
        exam=exam,
        attempt=attempt,
        questions=question_payload,
        seconds_remaining=attempt.seconds_remaining(),
    )


@exam_bp.route("/attempt/<int:attempt_id>/answer", methods=["POST"])
@login_required
def save_answer(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return jsonify({"error": "not authorized"}), 403

    if attempt.status != "in_progress":
        return jsonify({"error": "attempt already closed"}), 409

    if attempt.is_expired():
        _finalize_attempt(attempt, status="auto_submitted")
        db.session.commit()
        return jsonify({"error": "time_expired", "redirect": url_for("exam.results", attempt_id=attempt.id)}), 409

    data = request.get_json(force=True, silent=True) or {}
    question_id = data.get("question_id")
    option_id = data.get("option_id")

    if question_id is None:
        return jsonify({"error": "question_id required"}), 400

    question = Question.query.get_or_404(question_id)
    if question.exam_id != attempt.exam_id:
        return jsonify({"error": "question does not belong to this exam"}), 400

    answer = Answer.query.filter_by(attempt_id=attempt.id, question_id=question_id).first()
    if answer:
        answer.selected_option_id = option_id
        answer.answered_at = datetime.utcnow()
    else:
        answer = Answer(
            attempt_id=attempt.id,
            question_id=question_id,
            selected_option_id=option_id,
            answered_at=datetime.utcnow(),
        )
        db.session.add(answer)

    db.session.commit()

    return jsonify({
        "ok": True,
        "seconds_remaining": attempt.seconds_remaining(),
    })


@exam_bp.route("/attempt/<int:attempt_id>/violation", methods=["POST"])
@login_required
def log_violation(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return jsonify({"error": "not authorized"}), 403
    if attempt.status != "in_progress":
        return jsonify({"ok": True})

    data = request.get_json(force=True, silent=True) or {}
    violation_type = data.get("type", "unknown")
    allowed_types = {"tab_switch", "window_blur", "copy_attempt", "paste_attempt", "right_click"}
    if violation_type not in allowed_types:
        violation_type = "unknown"

    db.session.add(ExamViolation(attempt_id=attempt.id, violation_type=violation_type))
    db.session.commit()

    count = ExamViolation.query.filter_by(attempt_id=attempt.id).count()
    return jsonify({"ok": True, "violation_count": count})


@exam_bp.route("/attempt/<int:attempt_id>/heartbeat")
@login_required
def heartbeat(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return jsonify({"error": "not authorized"}), 403

    if attempt.status == "in_progress" and attempt.is_expired():
        _finalize_attempt(attempt, status="auto_submitted")
        db.session.commit()
        return jsonify({"expired": True, "redirect": url_for("exam.results", attempt_id=attempt.id)})

    return jsonify({"expired": False, "seconds_remaining": attempt.seconds_remaining()})


@exam_bp.route("/attempt/<int:attempt_id>/submit", methods=["POST"])
@login_required
def submit_exam(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        flash("Not authorized.", "error")
        return redirect(url_for("exam.list_exams"))

    if attempt.status == "in_progress":
        _finalize_attempt(attempt, status="submitted")
        db.session.commit()

    return redirect(url_for("exam.results", attempt_id=attempt.id))


@exam_bp.route("/attempt/<int:attempt_id>/results")
@login_required
def results(attempt_id):
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id and not current_user.is_teacher:
        flash("Not authorized.", "error")
        return redirect(url_for("exam.list_exams"))

    if attempt.status == "in_progress":
        flash("This exam is still in progress.", "info")
        return redirect(url_for("exam.take_exam", attempt_id=attempt.id))

    show_details = attempt.exam.results_published or current_user.is_teacher
    return render_template("results.html", attempt=attempt, show_details=show_details)


def _finalize_attempt(attempt, status):
    attempt.status = status
    attempt.submitted_at = datetime.utcnow()
    earned, total, percentage = compute_score(attempt)
    attempt.raw_score = earned
    attempt.total_marks_snapshot = total
    attempt.score = percentage
