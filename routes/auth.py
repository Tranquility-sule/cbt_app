import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user

from models import db, User

auth_bp = Blueprint("auth", __name__)

ALLOWED_PHOTO_EXTENSIONS = {"png", "jpg", "jpeg"}


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        reg_no = request.form.get("reg_no", "").strip()
        password = request.form.get("password", "").strip()

        user = User.query.filter(db.func.upper(User.reg_no) == reg_no.upper()).first()
        if user and user.check_password(password):
            login_user(user, remember=False)
            flash(f"Welcome, {user.name}.", "success")

            if user.must_change_password:
                return redirect(url_for("auth.change_password"))
            if user.is_teacher:
                return redirect(url_for("teacher.dashboard"))
            return redirect(url_for("exam.list_exams"))

        flash("Invalid registration number or password.", "error")

    return render_template("login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not current_user.check_password(current_password):
            flash("Your current password is incorrect.", "error")
            return redirect(url_for("auth.change_password"))

        if len(new_password) < 6:
            flash("New password must be at least 6 characters.", "error")
            return redirect(url_for("auth.change_password"))

        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for("auth.change_password"))

        current_user.set_password(new_password)
        current_user.must_change_password = False
        db.session.commit()

        flash("Password updated. Please log in with your new password next time.", "success")
        if current_user.is_teacher:
            return redirect(url_for("teacher.dashboard"))
        return redirect(url_for("exam.list_exams"))

    return render_template("change_password.html", forced=current_user.must_change_password)


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        file = request.files.get("photo")
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
            if ext not in ALLOWED_PHOTO_EXTENSIONS:
                flash("Please upload a PNG or JPG image.", "error")
                return redirect(url_for("auth.profile"))

            filename = f"user_{current_user.id}.{ext}"
            upload_dir = os.path.join(current_app.root_path, "static", "uploads", "profile_photos")
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, filename))

            current_user.profile_photo = filename
            db.session.commit()
            flash("Profile photo updated.", "success")
        else:
            flash("No photo selected.", "error")
        return redirect(url_for("auth.profile"))

    return render_template("profile.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
