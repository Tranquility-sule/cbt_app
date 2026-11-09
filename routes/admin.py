import csv
import io
import random
import string
import os
import shutil
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    Response, abort, send_file, current_app,
)
from flask_login import login_required, current_user

from models import db, User, School, Exam, Attendance
from access import owned_exam_or_404
from excel_export import build_credentials_workbook, build_attendance_workbook

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    if not current_user.is_admin:
        abort(403)


def _require_teacher():
    if not current_user.is_teacher:
        abort(403)


def _generate_password(length=8):
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def _next_reg_no(prefix):
    existing = User.query.filter(User.reg_no.like(f"{prefix}%")).all()
    max_num = 0
    for u in existing:
        suffix = u.reg_no[len(prefix):]
        if suffix.isdigit():
            max_num = max(max_num, int(suffix))
    return max_num + 1


@admin_bp.route("/admin/backup")
@login_required
def download_backup():
    _require_admin()

    db_uri = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not db_uri.startswith("sqlite:///"):
        flash(
            "Automatic backup download is only available for SQLite databases. "
            "This server appears to be using a different database — back it up "
            "using your database provider's own tools instead.",
            "error",
        )
        return redirect(url_for("admin.list_students"))

    db_path = db_uri.replace("sqlite:///", "", 1)
    if not os.path.exists(db_path):
        flash("Database file not found on this server.", "error")
        return redirect(url_for("admin.list_students"))

    # WAL mode (enabled for concurrent-write performance — see app.py)
    # keeps very recent transactions in a separate -wal file until they're
    # checkpointed back into the main file. Force that now so a plain
    # copy of cbt.db is guaranteed complete, not missing anything recent.
    db.session.execute(db.text("PRAGMA wal_checkpoint(FULL)"))

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_name = f"cbt_backup_{timestamp}.db"
    tmp_path = os.path.join(current_app.instance_path if current_app.instance_path else "/tmp", backup_name)
    os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
    shutil.copyfile(db_path, tmp_path)

    return send_file(
        tmp_path,
        as_attachment=True,
        download_name=backup_name,
        mimetype="application/octet-stream",
    )


@admin_bp.route("/admin/students")
@login_required
def list_students():
    _require_admin()
    students = User.query.filter_by(role="student").order_by(User.reg_no).all()
    return render_template("admin_students.html", students=students)


@admin_bp.route("/admin/students/<int:user_id>/reset-password", methods=["POST"])
@login_required
def reset_student_password(user_id):
    _require_admin()
    student = User.query.get_or_404(user_id)
    if student.role != "student":
        abort(400)

    new_password = _generate_password()
    student.set_password(new_password)
    student.must_change_password = True
    db.session.commit()

    flash(
        f"Password reset for {student.name} ({student.reg_no}). "
        f"New password: {new_password} — copy this now, it won't be shown again. "
        f"They'll be asked to choose their own password on next login.",
        "success",
    )
    return redirect(url_for("admin.list_students"))


@admin_bp.route("/admin/students/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_student(user_id):
    _require_admin()
    student = User.query.get_or_404(user_id)
    if student.role != "student":
        abort(400)

    if student.attempts:
        flash(
            f"Can't delete {student.name} ({student.reg_no}) — they've already "
            f"started or completed an exam, and removing them would break that "
            f"exam's results. Reset their password instead if needed.",
            "error",
        )
        return redirect(url_for("admin.list_students"))

    Attendance.query.filter_by(user_id=student.id).delete()
    name, reg_no = student.name, student.reg_no
    db.session.delete(student)
    db.session.commit()

    flash(f"Deleted account: {name} ({reg_no}).", "success")
    return redirect(url_for("admin.list_students"))


def _norm_name(name):
    return " ".join((name or "").lower().split())


def _duplicate_plan():
    """Group students by normalised name. Returns list of (keep, delete) lists.
    Kept: anyone with exam attempts or who already changed their password.
    If nobody qualifies, keep the lowest reg number. Everyone else is a delete."""
    groups = {}
    for s in User.query.filter_by(role="student").order_by(User.reg_no).all():
        groups.setdefault(_norm_name(s.name), []).append(s)
    plan = []
    for members in groups.values():
        if len(members) < 2:
            continue
        keep = [m for m in members if m.attempts or not m.must_change_password]
        if not keep:
            keep = [members[0]]
        delete = [m for m in members if m not in keep]
        if delete:
            plan.append((keep, delete))
    return plan


@admin_bp.route("/admin/students/duplicates", methods=["GET", "POST"])
@login_required
def clean_duplicates():
    _require_admin()
    plan = _duplicate_plan()
    if request.method == "POST":
        count = 0
        for keep, delete in plan:
            for s in delete:
                if s.attempts:
                    continue
                Attendance.query.filter_by(user_id=s.id).delete()
                db.session.delete(s)
                count += 1
        db.session.commit()
        flash(f"Removed {count} duplicate account(s). Now download a fresh credentials list.", "success")
        return redirect(url_for("admin.clean_duplicates"))
    return render_template("admin_duplicates.html", plan=plan)


@admin_bp.route("/admin/students/fresh-credentials", methods=["POST"])
@login_required
def fresh_credentials():
    """Reset passwords of every student who has not yet logged in and
    download ONE credentials sheet. Active students are left untouched."""
    _require_admin()
    pending = User.query.filter_by(role="student", must_change_password=True).order_by(User.reg_no).all()
    if not pending:
        flash("No students are awaiting first login.", "error")
        return redirect(url_for("admin.list_students"))
    accounts = []
    for s in pending:
        pw = _generate_password()
        s.set_password(pw)
        accounts.append({"name": s.name, "reg_no": s.reg_no, "password": pw})
    db.session.commit()
    data = build_credentials_workbook(accounts)
    return Response(
        data.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename=student_logins_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.xlsx"},
    )


@admin_bp.route("/admin/teachers", methods=["GET", "POST"])
@login_required
def list_teachers():
    _require_admin()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Enter the teacher's name.", "error")
            return redirect(url_for("admin.list_teachers"))
        limit = current_app.config.get("TEACHER_LIMIT", 15)
        if User.query.filter_by(role="teacher").count() >= limit:
            flash(
                f"Teacher limit reached ({limit}). Use \"Hand over\" on a teacher "
                f"who is finished to give their account to someone new.",
                "error",
            )
            return redirect(url_for("admin.list_teachers"))
        limit = current_app.config.get("MAX_TEACHERS", 15)
        if User.query.filter_by(role="teacher").count() >= limit:
            flash(
                f"Teacher limit reached ({limit}). Use \"Hand Over\" on a teacher who "
                f"has finished instead of creating a new account.",
                "error",
            )
            return redirect(url_for("admin.list_teachers"))
        num = _next_reg_no("TCH")
        reg_no = f"TCH{num:03d}"
        password = _generate_password()
        t = User(name=name, reg_no=reg_no, role="teacher")
        t.set_password(password)
        t.must_change_password = True
        db.session.add(t)
        db.session.commit()
        flash(
            f"Teacher created: {name} — Reg No: {reg_no}, Password: {password}. "
            f"Copy this now, it won't be shown again. They must choose their own "
            f"password on first login.",
            "success",
        )
        return redirect(url_for("admin.list_teachers"))
    teachers = User.query.filter_by(role="teacher").order_by(User.reg_no).all()
    counts = {t.id: Exam.query.filter_by(created_by=t.id).count() for t in teachers}
    return render_template("admin_teachers.html", teachers=teachers, counts=counts,
                           limit=current_app.config.get("TEACHER_LIMIT", 15))


@admin_bp.route("/admin/teachers/<int:user_id>/reset-password", methods=["POST"])
@login_required
def reset_teacher_password(user_id):
    _require_admin()
    t = User.query.get_or_404(user_id)
    if t.role != "teacher":
        abort(400)
    password = _generate_password()
    t.set_password(password)
    t.must_change_password = True
    db.session.commit()
    flash(
        f"Password reset for {t.name} ({t.reg_no}). New password: {password} — "
        f"copy it now, it won't be shown again.",
        "success",
    )
    return redirect(url_for("admin.list_teachers"))


@admin_bp.route("/admin/teachers/<int:user_id>/handover", methods=["POST"])
@login_required
def handover_teacher(user_id):
    """Give a finished teacher's account to a new person. Old exams and results
    move to the admin (nothing is deleted); the account gets a new name and a
    fresh password and starts with an empty dashboard."""
    _require_admin()
    t = User.query.get_or_404(user_id)
    if t.role != "teacher":
        abort(400)
    new_name = request.form.get("new_name", "").strip()
    if not new_name:
        flash("Enter the new teacher's name.", "error")
        return redirect(url_for("admin.list_teachers"))
    old_name = t.name
    moved = Exam.query.filter_by(created_by=t.id).update({"created_by": current_user.id})
    password = _generate_password()
    t.name = new_name
    t.set_password(password)
    t.must_change_password = True
    db.session.commit()
    flash(
        f"{t.reg_no} handed over from {old_name} to {new_name}. {moved} exam(s) moved to "
        f"the admin (results kept). New password: {password} — copy it now, it won't be "
        f"shown again.",
        "success",
    )
    return redirect(url_for("admin.list_teachers"))


@admin_bp.route("/admin/teachers/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_teacher(user_id):
    _require_admin()
    t = User.query.get_or_404(user_id)
    if t.role != "teacher":
        abort(400)
    if Exam.query.filter_by(created_by=t.id).count():
        flash(
            f"Can't delete {t.name} — they own exams. Their exams and results "
            f"would be left without an owner.",
            "error",
        )
        return redirect(url_for("admin.list_teachers"))
    name = t.name
    db.session.delete(t)
    db.session.commit()
    flash(f"Deleted teacher account: {name}.", "success")
    return redirect(url_for("admin.list_teachers"))


@admin_bp.route("/admin/students/bulk", methods=["GET", "POST"])
@login_required
def bulk_create_students():
    _require_admin()

    if request.method == "POST":
        file = request.files.get("student_list")
        prefix = request.form.get("prefix", "STU").strip().upper() or "STU"
        school_id = request.form.get("school_id") or None
        department = request.form.get("department", "").strip() or None

        if not file or file.filename == "":
            flash("Please upload a CSV file with a 'name' column.", "error")
            return redirect(url_for("admin.bulk_create_students"))

        try:
            content = file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            flash("Could not read the file. Please upload a plain CSV/text file.", "error")
            return redirect(url_for("admin.bulk_create_students"))

        names = []
        reader = csv.DictReader(io.StringIO(content))
        if reader.fieldnames and any(f.strip().lower() == "name" for f in reader.fieldnames):
            name_key = next(f for f in reader.fieldnames if f.strip().lower() == "name")
            for row in reader:
                n = (row.get(name_key) or "").strip()
                if n:
                    names.append(n)
        else:
            raw_lines = [line.strip() for line in content.splitlines() if line.strip()]
            lines_with_commas = [l for l in raw_lines if "," in l]
            if raw_lines and len(lines_with_commas) / len(raw_lines) > 0.3:
                flash(
                    "This file doesn't look like a plain name list — it has a 'name' "
                    "column missing and multiple comma-separated values per line. "
                    "If you're trying to re-upload a previously downloaded credentials "
                    "file, don't — that file is for distributing logins, not for "
                    "creating new ones. Upload a fresh file with just a 'name' column "
                    "(or one name per line) instead.",
                    "error",
                )
                return redirect(url_for("admin.bulk_create_students"))
            names = raw_lines

        if not names:
            flash("No student names found in the uploaded file.", "error")
            return redirect(url_for("admin.bulk_create_students"))

        allow_same = request.form.get("allow_same") == "1"
        skipped = []
        if not allow_same:
            seen = {_norm_name(u.name) for u in User.query.filter_by(role="student").all()}
            unique = []
            for n in names:
                key = _norm_name(n)
                if key in seen:
                    skipped.append(n)
                else:
                    seen.add(key)
                    unique.append(n)
            names = unique
            if not names:
                flash(
                    f"All {len(skipped)} name(s) already have accounts, so nothing was created. "
                    f"Use Students → Fresh Credentials List if you need new logins.",
                    "error",
                )
                return redirect(url_for("admin.bulk_create_students"))

        next_num = _next_reg_no(prefix)
        created_accounts = []

        for name in names:
            reg_no = f"{prefix}{next_num:03d}"
            while User.query.filter_by(reg_no=reg_no).first():
                next_num += 1
                reg_no = f"{prefix}{next_num:03d}"

            password = _generate_password()
            user = User(
                name=name,
                reg_no=reg_no,
                role="student",
                department=department,
                school_id=int(school_id) if school_id else None,
            )
            user.set_password(password)
            db.session.add(user)

            created_accounts.append({"name": name, "reg_no": reg_no, "password": password})
            next_num += 1

        db.session.commit()

        excel_bytes = build_credentials_workbook(created_accounts)
        msg = f"Created {len(created_accounts)} student account(s)."
        if skipped:
            msg += f" Skipped {len(skipped)} name(s) that already exist: " + ", ".join(skipped[:10]) + ("…" if len(skipped) > 10 else "")
        flash(msg, "success")

        return Response(
            excel_bytes.getvalue(),
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment;filename=student_logins_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.xlsx"
            },
        )

    schools = School.query.all()
    return render_template("admin_bulk_students.html", schools=schools)


@admin_bp.route("/admin/exams/<int:exam_id>/attendance")
@login_required
def view_attendance(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    records = Attendance.query.filter_by(exam_id=exam.id).order_by(Attendance.checked_in_at).all()
    return render_template("admin_attendance.html", exam=exam, records=records)


@admin_bp.route("/admin/exams/<int:exam_id>/attendance/export.xlsx")
@login_required
def export_attendance(exam_id):
    _require_teacher()
    exam = owned_exam_or_404(exam_id)
    records = Attendance.query.filter_by(exam_id=exam.id).order_by(Attendance.checked_in_at).all()

    excel_bytes = build_attendance_workbook(exam, records)

    return Response(
        excel_bytes.getvalue(),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment;filename={exam.title}_attendance.xlsx"},
    )
