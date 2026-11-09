"""
Non-destructive schema migration.

Whenever an update adds a new field to models.py, your existing cbt.db
won't have that column yet — SQLite doesn't auto-update its schema — and
you'll see errors like:
    sqlalchemy.exc.OperationalError: no such column: users.profile_photo

Run this instead of deleting cbt.db and re-seeding. It compares the
columns models.py expects against what's actually in your database file
and adds only what's missing, and rebuilds a table in place (preserving
every row) if an old constraint needs to be removed — for example, the
one-attempt-per-exam constraint that predates the retake feature.

Usage:
    python migrate.py

Safe to run any time, including when nothing has changed. Only supports
SQLite. If you've moved to Postgres/MySQL in production, use a proper
migration tool (e.g. Alembic) instead.
"""
import sqlite3
from sqlalchemy import Integer, Float, Boolean, DateTime

from app import create_app
from models import db

TYPE_MAP = [
    (Boolean, "INTEGER"),
    (Integer, "INTEGER"),
    (Float, "REAL"),
    (DateTime, "TEXT"),
]


def sqlite_type_for(col_type):
    for cls, sqlite_type in TYPE_MAP:
        if isinstance(col_type, cls):
            return sqlite_type
    return "TEXT"


def add_missing_columns(cur):
    added = []
    for table in db.metadata.sorted_tables:
        cur.execute(f"PRAGMA table_info('{table.name}')")
        existing_cols = {row[1] for row in cur.fetchall()}
        if not existing_cols:
            continue

        for col in table.columns:
            if col.name in existing_cols:
                continue
            sqlite_type = sqlite_type_for(col.type)
            cur.execute(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {sqlite_type}')
            added.append(f"{table.name}.{col.name}")
    return added


def find_obsolete_unique_index(cur, table_name, columns_set):
    """
    SQLite does NOT preserve a named constraint's declared name as the
    physical index name for inline table constraints — it auto-names the
    index (e.g. "sqlite_autoindex_exam_attempts_1") — so this matches by
    which columns the index actually covers, not by name.
    """
    cur.execute(f"PRAGMA index_list('{table_name}')")
    for row in cur.fetchall():
        index_name, is_unique = row[1], row[2]
        if not is_unique:
            continue
        cur.execute(f'PRAGMA index_info("{index_name}")')
        cols = {col_row[2] for col_row in cur.fetchall()}
        if cols == columns_set:
            return index_name
    return None


def rebuild_exam_attempts_without_unique_constraint(db_path):
    """
    SQLite refuses to DROP INDEX on an index tied to an inline table
    constraint — the only safe way to remove the constraint is the
    standard SQLite rebuild pattern: create a new table matching the
    current model (via SQLAlchemy, so it can never drift from models.py),
    copy every row across, then swap it in.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    index_name = find_obsolete_unique_index(cur, "exam_attempts", {"user_id", "exam_id"})
    if not index_name:
        conn.close()
        return False

    cur.execute("PRAGMA table_info('exam_attempts')")
    old_columns = [row[1] for row in cur.fetchall()]

    cur.execute("ALTER TABLE exam_attempts RENAME TO exam_attempts_old")
    conn.commit()
    conn.close()

    exam_attempts_table = db.metadata.tables["exam_attempts"]
    sa_conn = db.engine.connect()
    exam_attempts_table.create(bind=sa_conn)
    sa_conn.commit()
    sa_conn.close()

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA table_info('exam_attempts')")
    new_columns = {row[1] for row in cur.fetchall()}
    common_columns = [c for c in old_columns if c in new_columns]

    # A column that's NOT NULL in the model but was just added to the old
    # table moments ago (via add_missing_columns) has NULL on every
    # existing row — Python-side ORM defaults don't apply to raw SQL.
    # COALESCE it to a safe literal so copying old rows into the new,
    # strictly-enforced table doesn't violate that NOT NULL constraint.
    sa_columns = {c.name: c for c in exam_attempts_table.columns}
    select_parts = []
    for c in common_columns:
        sa_col = sa_columns.get(c)
        if sa_col is not None and not sa_col.nullable:
            select_parts.append(f'COALESCE("{c}", 0)')
        else:
            select_parts.append(f'"{c}"')

    insert_col_list = ", ".join(f'"{c}"' for c in common_columns)
    select_list = ", ".join(select_parts)

    cur.execute(f'INSERT INTO exam_attempts ({insert_col_list}) SELECT {select_list} FROM exam_attempts_old')
    cur.execute("DROP TABLE exam_attempts_old")
    conn.commit()
    conn.close()

    return True


def main():
    app = create_app()
    with app.app_context():
        uri = app.config["SQLALCHEMY_DATABASE_URI"]
        if not uri.startswith("sqlite:///"):
            print("This script only supports SQLite. For Postgres/MySQL in "
                  "production, use a proper migration tool (e.g. Alembic).")
            return

        db_path = uri.replace("sqlite:///", "", 1)

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        added = add_missing_columns(cur)
        conn.commit()
        conn.close()

        rebuilt = False
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exam_attempts'")
        table_exists = cur.fetchone() is not None
        conn.close()

        if table_exists:
            rebuilt = rebuild_exam_attempts_without_unique_constraint(db_path)

        if added:
            print(f"Migration complete. Added {len(added)} column(s), no data was touched:")
            for a in added:
                print("  -", a)
        if rebuilt:
            print("Removed the old one-attempt-per-exam constraint (needed for exam retakes) — all existing attempts preserved.")
        if not added and not rebuilt:
            print("Schema already up to date — nothing to migrate.")


if __name__ == "__main__":
    main()
