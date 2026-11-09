from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class School(db.Model):
    __tablename__ = "schools"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)

    users = db.relationship("User", backref="school", lazy=True)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    reg_no = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")  # admin | teacher | student
    must_change_password = db.Column(db.Boolean, default=True, nullable=False)
    profile_photo = db.Column(db.String(255), nullable=True)  # filename under static/uploads/profile_photos/, optional
    department = db.Column(db.String(100), nullable=True)  # e.g. "Computer Science" — optional, used to restrict exam access

    attempts = db.relationship("ExamAttempt", backref="user", lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_teacher(self):
        return self.role in ("teacher", "admin")

    @property
    def is_admin(self):
        return self.role == "admin"


class Exam(db.Model):
    __tablename__ = "exams"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    class_level = db.Column(db.String(50), nullable=True)  # e.g. "SS3" — optional, purely display
    restricted_department = db.Column(db.String(100), nullable=True)  # blank/None = open to every student
    locked = db.Column(db.Boolean, default=True, nullable=False)  # locked by default — teacher must explicitly unlock
    duration_minutes = db.Column(db.Integer, nullable=False, default=30)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    shuffle_questions = db.Column(db.Boolean, default=True)
    shuffle_options = db.Column(db.Boolean, default=True)
    pass_mark = db.Column(db.Float, default=50.0)  # percentage
    results_published = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    questions = db.relationship(
        "Question", backref="exam", lazy=True, order_by="Question.order_index",
        cascade="all, delete-orphan",
    )
    attempts = db.relationship("ExamAttempt", backref="exam", lazy=True)

    def total_marks(self):
        return sum(q.marks for q in self.questions)

    def is_open_now(self):
        if self.locked:
            return False
        now = datetime.utcnow()
        if self.start_time and now < self.start_time:
            return False
        if self.end_time and now > self.end_time:
            return False
        return True

    def is_open_for(self, user):
        """Combines the lock/schedule check with department eligibility.
        A blank restricted_department means the exam is open to everyone."""
        if not self.is_open_now():
            return False
        if not self.restricted_department:
            return True
        student_dept = (user.department or "").strip().lower()
        return student_dept == self.restricted_department.strip().lower()

    def attempt_for(self, user_id):
        """
        Returns the student's current, authoritative attempt — the most
        recent one that hasn't been superseded by a granted retake (or
        permanently deleted via "Delete Score", in which case it simply
        won't be in self.attempts at all). If a retake was granted on the
        latest attempt, this returns None even though older attempt rows
        still exist in the database, so the student's dashboard correctly
        shows them as free to start fresh.
        """
        candidates = sorted(
            [a for a in self.attempts if a.user_id == user_id],
            key=lambda a: a.started_at, reverse=True,
        )
        if not candidates:
            return None
        latest = candidates[0]
        return None if latest.retake_granted else latest

    def all_attempts_for(self, user_id):
        """Full history for a student on this exam, newest first — includes
        attempts superseded by a retake, so nothing is ever hidden."""
        return sorted(
            [a for a in self.attempts if a.user_id == user_id],
            key=lambda a: a.started_at, reverse=True,
        )


class Question(db.Model):
    __tablename__ = "questions"
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    text = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    question_type = db.Column(db.String(20), default="mcq")
    marks = db.Column(db.Float, default=1.0)
    order_index = db.Column(db.Integer, default=0)

    options = db.relationship(
        "Option", backref="question", lazy=True, order_by="Option.order_index",
        cascade="all, delete-orphan",
    )


class Option(db.Model):
    __tablename__ = "options"
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    is_correct = db.Column(db.Boolean, default=False)
    order_index = db.Column(db.Integer, default=0)


class ExamAttempt(db.Model):
    __tablename__ = "exam_attempts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default="in_progress")  # in_progress | submitted | auto_submitted
    score = db.Column(db.Float, nullable=True)  # percentage — used internally for pass/fail comparison only
    raw_score = db.Column(db.Float, nullable=True)  # marks actually earned, e.g. 23
    total_marks_snapshot = db.Column(db.Float, nullable=True)  # exam's total marks at submission time, e.g. 40
    retake_granted = db.Column(db.Boolean, default=False, nullable=False)  # teacher explicitly allowed a fresh attempt after this one

    # Seed used to deterministically shuffle question/option order for this
    # specific attempt. Stored so refreshes don't re-shuffle the student's view.
    shuffle_seed = db.Column(db.Integer, nullable=False)

    answers = db.relationship(
        "Answer", backref="attempt", lazy=True, cascade="all, delete-orphan"
    )
    violations = db.relationship(
        "ExamViolation", backref="attempt", lazy=True, cascade="all, delete-orphan"
    )

    # No DB-level uniqueness on (user_id, exam_id) — a retake creates a new
    # row rather than overwriting the old one. "Only one ACTIVE attempt at
    # a time" is enforced in application logic (routes/exam.py: start_exam),
    # which ignores attempts with retake_granted=True when checking for an
    # existing attempt. This is what makes a retake possible without ever
    # deleting or mutating the original graded result.

    def deadline(self):
        return self.started_at + timedelta(minutes=self.exam.duration_minutes)

    def seconds_remaining(self):
        remaining = (self.deadline() - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))

    def is_expired(self):
        return datetime.utcnow() >= self.deadline()


class Attendance(db.Model):
    """
    Recorded automatically the moment a student starts an exam (see
    routes/exam.py: start_exam). One row per student per exam — this is
    the source of truth for "who actually sat the exam", independent of
    whether they went on to submit, got auto-submitted, or abandoned it.
    Deliberately untouched by score deletion/retake — attendance is about
    presence, not performance.
    """
    __tablename__ = "attendance"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    reg_no = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    checked_in_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")
    exam = db.relationship("Exam")

    __table_args__ = (
        db.UniqueConstraint("user_id", "exam_id", name="uq_user_exam_attendance"),
    )


class ExamViolation(db.Model):
    """
    Logs a suspected integrity violation during an exam attempt — tab
    switch, window minimized/blurred, or a blocked copy/paste attempt.
    Purely informational: nothing here auto-submits or penalizes the
    student. The teacher reviews the count and decides what to do.
    """
    __tablename__ = "exam_violations"
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("exam_attempts.id"), nullable=False)
    violation_type = db.Column(db.String(30), nullable=False)  # tab_switch | window_blur | copy_attempt | paste_attempt | right_click
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow)


class Answer(db.Model):
    __tablename__ = "answers"
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey("exam_attempts.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    selected_option_id = db.Column(db.Integer, db.ForeignKey("options.id"), nullable=True)
    answered_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    question = db.relationship("Question")
    selected_option = db.relationship("Option")

    __table_args__ = (
        db.UniqueConstraint("attempt_id", "question_id", name="uq_attempt_question"),
    )
