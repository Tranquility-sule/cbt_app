import csv
import io

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    Response, abort,
)
from flask_login import login_required, current_user

from models import db, Exam, Question, Option, ExamAttempt, Attendance
from excel_export import build_results_workbook
from document_import import parse_uploaded_file
from access import owned_exam_or_404

teacher_bp = Blueprint("teacher", __name__)


def _require_teacher():
    if not current_user.is_teacher:
        abort(403)


@teacher_bp.route("/teacher")
@login_required
def dashboard():
    _require_teacher()
    query = Exam.query
    if not current_user.is_admin:
        query = query.filter(Exam.created_by == current_user.id)
    exams = query.order_by(Exam.created_at.desc()).all()
    return render_template("teacher_dashboard.html", exams=exams)


@teacher_bp.route("/teacher/exams/new", methods=["GET", "POST"])
@login_required
def new_exam():
    _require_teacher()
    if request.method == "POST":
        exam = Exam(
            title=request.form["title"],
            subject=request.form["subject"],
            class_level=request.form.get("class_level", "").strip() or None,
            restricted_department=request.form.get("restricted_department", "").strip() or None,
            duration_minutes=int(request.form["duration_minutes"]),
            shuffle_questions=bool(request.form.get("shuffle_questions")),
            shuffle_options=bool(request.form.get("shuffle_options")),
            pass_mark=float(request.form.get("pass_mark", 50)),
            locked=not bool(request.form.get("unlock_immediately")),
            created_by=current_user.id,
        )
        db.session.add(exam)
        db.session.commit()
        flash("Exam created. Now add questions.", "success")
        return redirect(url_for("teacher.edit_exam", exam_id=exam.id))

    return render_template("exam_form.html", exam=None)


@teacher_bp.route("/teacher/exams/<int:exam_id>")
@login_required
def edit_exam(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    return render_template("exam_edit.html", exam=exam)


@teacher_bp.route("/teacher/exams/<int:exam_id>/edit-details", methods=["GET", "POST"])
@login_required
def edit_exam_details(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    if request.method == "POST":
        exam.title = request.form["title"].strip()
        exam.subject = request.form["subject"].strip()
        exam.class_level = request.form.get("class_level", "").strip() or None
        exam.restricted_department = request.form.get("restricted_department", "").strip() or None
        exam.duration_minutes = int(request.form["duration_minutes"])
        exam.pass_mark = float(request.form.get("pass_mark", 50))
        exam.shuffle_questions = bool(request.form.get("shuffle_questions"))
        exam.shuffle_options = bool(request.form.get("shuffle_options"))
        db.session.commit()
        flash(
            "Exam details updated. Note: this renames the exam everywhere, including "
            "on any results already submitted under its old name — the title isn't "
            "frozen at submission time.",
            "success",
        )
        return redirect(url_for("teacher.edit_exam", exam_id=exam.id))

    return render_template("edit_exam_details.html", exam=exam)


@teacher_bp.route("/teacher/exams/<int:exam_id>/delete", methods=["POST"])
@login_required
def delete_exam(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    attempt_count = len(exam.attempts)
    if attempt_count > 0:
        flash(
            f"Can't delete \"{exam.title}\" — {attempt_count} student attempt(s) "
            f"already exist for it, and deleting it would break their results and "
            f"any exports referencing it. Use \"Lock\" instead to stop further "
            f"attempts while keeping existing results intact.",
            "error",
        )
        return redirect(url_for("teacher.dashboard"))

    Attendance.query.filter_by(exam_id=exam.id).delete()
    title = exam.title
    db.session.delete(exam)
    db.session.commit()

    flash(f"Deleted exam: {title}.", "success")
    return redirect(url_for("teacher.dashboard"))


@teacher_bp.route("/teacher/exams/<int:exam_id>/toggle-lock", methods=["POST"])
@login_required
def toggle_lock(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    exam.locked = not exam.locked
    db.session.commit()
    flash(
        f"{exam.subject} is now {'locked' if exam.locked else 'unlocked and available to students'}.",
        "info" if exam.locked else "success",
    )
    return redirect(request.referrer or url_for("teacher.dashboard"))


@teacher_bp.route("/teacher/exams/<int:exam_id>/questions/<int:question_id>/edit", methods=["GET", "POST"])
@login_required
def edit_question(exam_id, question_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    question = Question.query.get_or_404(question_id)
    if question.exam_id != exam.id:
        abort(404)

    if request.method == "POST":
        question.text = request.form["text"]
        question.marks = float(request.form.get("marks", 1))

        option_texts = request.form.getlist("option_text")
        correct_index = int(request.form.get("correct_option", 0))

        existing_options = sorted(question.options, key=lambda o: o.order_index)

        for i in range(5):
            text = option_texts[i].strip() if i < len(option_texts) else ""
            is_correct = (i == correct_index) and bool(text)

            if i < len(existing_options):
                opt = existing_options[i]
                opt.text = text
                opt.is_correct = is_correct
            elif text:
                db.session.add(Option(
                    question_id=question.id, text=text,
                    is_correct=is_correct, order_index=i,
                ))

        db.session.commit()
        flash("Question updated.", "success")
        return redirect(url_for("teacher.edit_exam", exam_id=exam.id))

    options = sorted(question.options, key=lambda o: o.order_index)
    return render_template("edit_question.html", exam=exam, question=question, options=options)


@teacher_bp.route("/teacher/exams/<int:exam_id>/questions/<int:question_id>/delete", methods=["POST"])
@login_required
def delete_question(exam_id, question_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    question = Question.query.get_or_404(question_id)
    if question.exam_id != exam.id:
        abort(404)

    db.session.delete(question)
    db.session.commit()
    flash("Question deleted.", "success")
    return redirect(url_for("teacher.edit_exam", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/questions/new", methods=["POST"])
@login_required
def add_question(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    question = Question(
        exam_id=exam.id,
        text=request.form["text"],
        marks=float(request.form.get("marks", 1)),
        order_index=len(exam.questions),
    )
    db.session.add(question)
    db.session.flush()

    option_texts = request.form.getlist("option_text")
    correct_index = int(request.form.get("correct_option", 0))
    for i, text in enumerate(option_texts):
        if not text.strip():
            continue
        db.session.add(Option(
            question_id=question.id,
            text=text.strip(),
            is_correct=(i == correct_index),
            order_index=i,
        ))

    db.session.commit()
    flash("Question added.", "success")
    return redirect(url_for("teacher.edit_exam", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/questions/bulk", methods=["POST"])
@login_required
def bulk_add_questions(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    file = request.files.get("questions_file")
    if not file or file.filename == "":
        flash("Please upload a CSV file.", "error")
        return redirect(url_for("teacher.edit_exam", exam_id=exam.id))

    try:
        content = file.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        flash("Could not read the file. Please upload a plain CSV file.", "error")
        return redirect(url_for("teacher.edit_exam", exam_id=exam.id))

    reader = csv.DictReader(io.StringIO(content))
    fieldnames = [f.strip().lower() for f in (reader.fieldnames or [])]

    required = {"question", "option_a", "option_b", "correct"}
    if not required.issubset(set(fieldnames)):
        flash(
            "CSV must have at least these columns: question, option_a, option_b, "
            "correct (plus optional option_c, option_d, option_e, marks). "
            f"Found columns: {', '.join(fieldnames) if fieldnames else '(none)'}",
            "error",
        )
        return redirect(url_for("teacher.edit_exam", exam_id=exam.id))

    reader = csv.DictReader(io.StringIO(content))
    reader.fieldnames = [f.strip().lower() for f in reader.fieldnames]

    letter_to_col = {"a": "option_a", "b": "option_b", "c": "option_c", "d": "option_d", "e": "option_e"}
    start_index = len(exam.questions)
    created = 0
    skipped = 0

    for row in reader:
        question_text = (row.get("question") or "").strip()
        if not question_text:
            continue

        correct_letter = (row.get("correct") or "").strip().lower()
        if correct_letter not in letter_to_col:
            skipped += 1
            continue

        option_texts = []
        for letter in ["a", "b", "c", "d", "e"]:
            text = (row.get(letter_to_col[letter]) or "").strip()
            option_texts.append(text)

        if not option_texts[0] or not option_texts[1]:
            skipped += 1
            continue

        try:
            marks = float(row.get("marks") or 1)
        except ValueError:
            marks = 1.0

        question = Question(
            exam_id=exam.id,
            text=question_text,
            marks=marks,
            order_index=start_index + created,
        )
        db.session.add(question)
        db.session.flush()

        correct_index = ["a", "b", "c", "d", "e"].index(correct_letter)
        for i, text in enumerate(option_texts):
            if not text:
                continue
            db.session.add(Option(
                question_id=question.id,
                text=text,
                is_correct=(i == correct_index),
                order_index=i,
            ))
        created += 1

    db.session.commit()

    if created:
        flash(f"Imported {created} question(s)." + (f" Skipped {skipped} invalid row(s)." if skipped else ""), "success")
    else:
        flash("No valid questions found in the file. Check the format and try again.", "error")

    return redirect(url_for("teacher.edit_exam", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/questions/import-document", methods=["GET", "POST"])
@login_required
def import_document(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    if request.method == "GET":
        return render_template("import_document.html", exam=exam)

    file = request.files.get("document")
    if not file or file.filename == "":
        flash("Please choose a .docx or .pdf file to upload.", "error")
        return redirect(url_for("teacher.import_document", exam_id=exam.id))

    questions, error = parse_uploaded_file(file)
    if error:
        flash(error, "error")
        return redirect(url_for("teacher.import_document", exam_id=exam.id))

    return render_template("import_document_preview.html", exam=exam, questions=questions)


@teacher_bp.route("/teacher/exams/<int:exam_id>/questions/import-document/confirm", methods=["POST"])
@login_required
def confirm_document_import(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    try:
        question_count = int(request.form.get("question_count", 0))
    except ValueError:
        question_count = 0

    start_index = len(exam.questions)
    created = 0
    letters = ["A", "B", "C", "D", "E"]

    for i in range(question_count):
        if not request.form.get(f"q{i}_include"):
            continue

        text = (request.form.get(f"q{i}_text") or "").strip()
        correct_letter = request.form.get(f"q{i}_correct")
        if not text or not correct_letter:
            continue

        option_texts = {}
        for letter in letters:
            val = (request.form.get(f"q{i}_option_{letter}") or "").strip()
            if val:
                option_texts[letter] = val

        if len(option_texts) < 2 or correct_letter not in option_texts:
            continue

        question = Question(
            exam_id=exam.id,
            text=text,
            marks=1.0,
            order_index=start_index + created,
        )
        db.session.add(question)
        db.session.flush()

        for letter, opt_text in option_texts.items():
            db.session.add(Option(
                question_id=question.id,
                text=opt_text,
                is_correct=(letter == correct_letter),
                order_index=letters.index(letter),
            ))
        created += 1

    db.session.commit()

    if created:
        flash(f"Imported {created} question(s) from the document.", "success")
    else:
        flash("No questions were imported — nothing was checked/confirmed.", "error")

    return redirect(url_for("teacher.edit_exam", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/publish", methods=["POST"])
@login_required
def toggle_publish(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    exam.results_published = not exam.results_published
    db.session.commit()
    flash(
        "Results published." if exam.results_published else "Results hidden.",
        "info",
    )
    return redirect(url_for("teacher.exam_results", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/attempts/<int:attempt_id>/allow-retake", methods=["POST"])
@login_required
def allow_retake(exam_id, attempt_id):
    """Archives the old attempt IN PLACE — score, answers, and timestamp
    are never touched, just flagged as superseded — and frees the student
    to start a brand-new attempt."""
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.exam_id != exam.id:
        abort(404)

    if attempt.status == "in_progress":
        flash("Can't grant a retake on an exam that's still in progress — wait for it to finish or expire first.", "error")
        return redirect(url_for("teacher.exam_results", exam_id=exam.id))

    attempt.retake_granted = True
    db.session.commit()

    flash(
        f"Retake granted for {attempt.user.name} ({attempt.user.reg_no}). "
        f"Their previous score is preserved and still visible below — "
        f"they can now start a fresh attempt.",
        "success",
    )
    return redirect(url_for("teacher.exam_results", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/restart-all", methods=["POST"])
@login_required
def restart_all(exam_id):
    """Bulk version of allow_retake — grants a retake to every student who
    has completed this exam, in one click, WITHOUT deleting anyone's
    existing score. Use this after fixing an exam so the whole class can
    redo it while every original score stays on record, clearly marked
    as superseded."""
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    eligible = [
        a for a in exam.attempts
        if a.status != "in_progress" and not a.retake_granted
    ]
    for attempt in eligible:
        attempt.retake_granted = True
    db.session.commit()

    if eligible:
        flash(
            f"Restarted the exam for {len(eligible)} student(s) — every original "
            f"score is preserved and still visible below, marked as superseded.",
            "success",
        )
    else:
        flash("No eligible attempts to restart — everyone is either mid-exam or already restarted.", "info")
    return redirect(url_for("teacher.exam_results", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/attempts/<int:attempt_id>/delete-score", methods=["POST"])
@login_required
def delete_score(exam_id, attempt_id):
    """The destructive counterpart to allow_retake — PERMANENTLY erases a
    specific attempt (its score, every answer, every logged violation)
    rather than just archiving it. This also frees the student to start a
    fresh attempt, same as a retake, but leaves no trace of the old one.
    Irreversible — there is no undo, no backup of the deleted row."""
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    attempt = ExamAttempt.query.get_or_404(attempt_id)
    if attempt.exam_id != exam.id:
        abort(404)

    if attempt.status == "in_progress":
        flash("Can't delete a score for an exam that's still in progress — wait for it to finish or expire first.", "error")
        return redirect(url_for("teacher.exam_results", exam_id=exam.id))

    student_name, student_reg_no = attempt.user.name, attempt.user.reg_no
    db.session.delete(attempt)  # cascades to Answer and ExamViolation rows
    db.session.commit()

    flash(
        f"Permanently deleted the score for {student_name} ({student_reg_no}). "
        f"This cannot be undone. They can now start a fresh attempt.",
        "success",
    )
    return redirect(url_for("teacher.exam_results", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/delete-all-scores", methods=["POST"])
@login_required
def delete_all_scores(exam_id):
    """Bulk, PERMANENT deletion of every completed attempt on this exam.
    Irreversible. Use restart_all instead if you want to preserve history —
    this wipes it entirely, for when you genuinely don't want the old
    (possibly wrong) scores cluttering your records at all."""
    _require_teacher()
    exam = owned_exam_or_404(exam_id)

    deletable = [a for a in exam.attempts if a.status != "in_progress"]
    count = len(deletable)
    for attempt in deletable:
        db.session.delete(attempt)
    db.session.commit()

    if count:
        flash(f"Permanently deleted {count} score(s) for this exam. This cannot be undone.", "success")
    else:
        flash("No completed attempts to delete.", "info")
    return redirect(url_for("teacher.exam_results", exam_id=exam.id))


@teacher_bp.route("/teacher/exams/<int:exam_id>/results")
@login_required
def exam_results(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    attempts = [a for a in exam.attempts if a.status != "in_progress"]

    current_attempts = [a for a in attempts if not a.retake_granted]

    raw_scores = [a.raw_score for a in current_attempts if a.raw_score is not None]
    total_marks = exam.total_marks()
    stats = {
        "count": len(raw_scores),
        "average": round(sum(raw_scores) / len(raw_scores), 1) if raw_scores else 0,
        "highest": max(raw_scores) if raw_scores else 0,
        "lowest": min(raw_scores) if raw_scores else 0,
        "total_marks": total_marks,
        "pass_count": sum(1 for a in current_attempts if a.score is not None and a.score >= exam.pass_mark),
        "fail_count": sum(1 for a in current_attempts if a.score is not None and a.score < exam.pass_mark),
    }

    question_stats = []
    for q in exam.questions:
        total = 0
        wrong = 0
        for a in current_attempts:
            ans = next((x for x in a.answers if x.question_id == q.id), None)
            if ans is None:
                continue
            total += 1
            correct_opt = next((o for o in q.options if o.is_correct), None)
            if not correct_opt or ans.selected_option_id != correct_opt.id:
                wrong += 1
        pct_wrong = round((wrong / total) * 100, 1) if total else 0
        question_stats.append({"question": q, "pct_wrong": pct_wrong, "total_answered": total})

    attempts.sort(key=lambda a: (a.user.reg_no, -a.started_at.timestamp()))

    return render_template(
        "teacher_results.html", exam=exam, attempts=attempts, stats=stats,
        question_stats=question_stats,
    )


@teacher_bp.route("/teacher/exams/<int:exam_id>/export.csv")
@login_required
def export_csv(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    attempts = [a for a in exam.attempts if a.status != "in_progress"]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Student Name", "Reg No", "Score", "Total Marks", "Outcome", "Status", "Flags", "Retake Status", "Submitted At"])
    for a in attempts:
        outcome = ""
        if a.score is not None:
            outcome = "PASS" if a.score >= exam.pass_mark else "FAIL"
        writer.writerow([
            a.user.name, a.user.reg_no,
            a.raw_score if a.raw_score is not None else "",
            a.total_marks_snapshot if a.total_marks_snapshot is not None else exam.total_marks(),
            outcome, a.status, len(a.violations),
            "Superseded (retake given)" if a.retake_granted else "Current",
            a.submitted_at.strftime("%Y-%m-%d %H:%M") if a.submitted_at else "",
        ])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={exam.title}_results.csv"},
    )


@teacher_bp.route("/teacher/exams/<int:exam_id>/export.xlsx")
@login_required
def export_xlsx(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    attempts = [a for a in exam.attempts if a.status != "in_progress"]

    excel_bytes = build_results_workbook(exam, attempts)

    return Response(
        excel_bytes.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename={exam.title}_results.xlsx"},
    )
