import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-this-in-production")
    MAX_TEACHERS = int(os.environ.get("MAX_TEACHERS", 15))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(basedir, 'cbt.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Maximum number of teacher accounts the admin can create.
    TEACHER_LIMIT = int(os.environ.get("TEACHER_LIMIT", 15))

    AUTOSUBMIT_SWEEP_SECONDS = 30
    CLIENT_CLOCK_GRACE_SECONDS = 3
    PERMANENT_SESSION_LIFETIME = timedelta(hours=6)
    MAX_CONTENT_LENGTH = 3 * 1024 * 1024  # 3MB cap, mainly for profile photo uploads

    # SQLite's default single-writer lock is the real bottleneck under
    # concurrent exam-start traffic, not the web server's thread count.
    # A longer busy_timeout makes a competing writer wait its turn instead
    # of failing outright with "database is locked". WAL mode (enabled via
    # the connection event listener in app.py) is what actually lets a
    # writer and readers coexist without blocking each other.
    SQLALCHEMY_ENGINE_OPTIONS = {"connect_args": {"timeout": 30}}
