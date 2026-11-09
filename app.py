import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from sqlalchemy import event

from config import Config
from models import db, User


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    # WAL (Write-Ahead Logging) mode is what actually lets SQLite handle
    # many students starting an exam at once without piling up behind a
    # single-writer lock — a reader no longer blocks a writer or vice
    # versa. Set on every new connection, since it's a per-connection
    # pragma, not a database-file-level setting that persists on its own.
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite:///"):
        with app.app_context():
            @event.listens_for(db.engine, "connect")
            def enable_wal_mode(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from routes.auth import auth_bp
    from routes.exam import exam_bp
    from routes.teacher import teacher_bp
    from routes.admin import admin_bp
    from routes.support import support_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(exam_bp)
    app.register_blueprint(teacher_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(support_bp)

    @app.before_request
    def enforce_password_change():
        if not current_user.is_authenticated:
            return
        if not current_user.must_change_password:
            return
        from flask import request
        allowed = {"auth.change_password", "auth.logout", "static"}
        if request.endpoint not in allowed:
            return redirect(url_for("auth.change_password"))

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    with app.app_context():
        db.create_all()

    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not app.debug:
        from sweeper import start_sweeper
        start_sweeper(app)
    elif os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from sweeper import start_sweeper
        start_sweeper(app)

    return app


if __name__ == "__main__":
    app = create_app()
    # threaded=True matters once more than a handful of people use this at
    # once — without it, every request (login, page load, answer save)
    # queues behind whichever one is currently running, one at a time.
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
