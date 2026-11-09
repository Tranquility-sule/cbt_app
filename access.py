"""Ownership rules: a teacher can only see/change exams they created.
Admins can see and manage every exam."""
from flask import abort
from flask_login import current_user

from models import Exam


def can_manage(exam):
    if current_user.is_admin:
        return True
    return exam.created_by is not None and exam.created_by == current_user.id


def owned_exam_or_404(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not can_manage(exam):
        # 404 (not 403) so a teacher can't even tell the exam exists.
        abort(404)
    return exam
