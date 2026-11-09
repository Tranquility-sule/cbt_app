# School CBT — Computer-Based Testing System

A web-based Computer-Based Testing (CBT) platform built entirely in **Python (Flask)**.
Students log in with their own registration number, write timed objective exams, and get
their scores instantly. Teachers and admins create exams, manage students and download results.

## Features

**Students**
- Individual login (registration number + password); forced password change on first login
- Subject dashboard with status badges (Active / In Progress / Done)
- Server-controlled countdown timer, auto-submit when time is up
- Answers autosave and retry if the network drops
- Instant results shown as raw marks (e.g. `23 / 40`) with Pass/Fail
- Optional profile photo and a built-in support chatbot (FAQ)

**Teachers**
- Create/edit exams; add questions manually, by CSV, or import from **Word / PDF**
- Up to 5 options (A–E) per question; question and option shuffling per student
- Lock/unlock exams, restrict an exam to a department
- Results dashboard, per-question analysis, CSV and Excel export
- Private by design: a teacher only sees and manages the exams they created; other teachers' exams are invisible to them
- Allow retake (one student or the whole class) without losing old scores
- Integrity log: tab switches, minimising, copy/paste and right-click attempts (informational only)

**Admins**
- Bulk-create student accounts from a name list; downloads an Excel sheet of logins
- **Teacher accounts:** create teachers (TCH001, TCH002, ...) each with their own password, reset passwords,
  and **Hand Over** a finished teacher's account to someone new (old exams move to the admin, results kept).
  Capped at 15 teachers by default (`MAX_TEACHERS`)
- Reset passwords, delete unused accounts, **find and remove duplicate accounts**,
  and issue a **fresh credentials list** for students who haven't logged in yet
- Automatic attendance records and Excel download
- One-click database backup

---

## Tech stack

Python 3 · Flask · Flask-SQLAlchemy · Flask-Login · SQLite (WAL mode) · APScheduler ·
Waitress (production server) · openpyxl · python-docx · pdfplumber · Jinja2 · vanilla JS

## Quick start

```bash
git clone https://github.com/Tranquility-sule/cbt_app.git
cd cbt_app
python -m venv venv
venv\Scripts\activate            # Windows   (Linux/macOS: source venv/bin/activate)
pip install -r requirements.txt
python seed.py                   # demo accounts + sample exam
python app.py                    # http://localhost:5000
```

Demo logins created by `seed.py` (**change or delete these before real use**):

| Role    | Reg No   | Password   |
|---------|----------|------------|
| Admin   | ADMIN001 | admin123   |
| Teacher | TCH001   | teacher123 |
| Student | STU001   | student123 |

### Running an exam for many students (same Wi-Fi / LAN)

```bash
python run_production.py
```

Find your computer's IPv4 address with `ipconfig` and give students
`http://<your-ip>:5000`. Everyone must be on the same network, and the
firewall must allow port 5000.

### Updating without losing data

After pulling a new version, run `python migrate.py`. It adds any missing columns
and never deletes data. **Never delete `cbt.db` to fix a "no such column" error.**


## Adding students

1. Admin → **Students → Bulk Add Students**
2. Upload a `.csv` with a `name` column (see `student_list_template.csv`) or a `.txt` with one name per line
3. Download the generated Excel sheet and give each student their login

Names that already have an account are skipped, so re-uploading can't create duplicates.
If duplicates already exist: **Students → Clean Duplicates**, then **Fresh Credentials List**.


## Project structure

```
app.py              App factory and startup
run_production.py   Waitress production server
config.py           Settings (DB path, secret key)
models.py           Database models
access.py           Exam ownership rules (teacher privacy)
grading.py          Auto-grading
shuffle.py          Per-student question/option ordering
sweeper.py          Background auto-submit of expired attempts
document_import.py  Word/PDF question parser
excel_export.py     Excel/CSV report builders
faq_data.py         Support chatbot answers
migrate.py          Non-destructive schema updater
seed.py             Demo data
routes/             auth, exam, teacher, admin, support blueprints
templates/ static/  Jinja2 pages, CSS, images
docs/               Detailed development notes
```


## Security notes

- Passwords are stored hashed (scrypt) and can only be reset, never viewed
- Roles: admin (one account, sees everything), teacher (own exams only), student (own attempts; department-restricted exams enforced server-side)
- Set `SECRET_KEY` (and optionally `DATABASE_URL`) as environment variables in production
- **Never commit `cbt.db`, backups or credential spreadsheets** — they contain student data (see `.gitignore`)
- Integrity monitoring discourages casual cheating; it is not full proctoring

## Known limitations

- Only objective (MCQ / true-false) questions are auto-graded
- SQLite is fine for a class or hall; consider PostgreSQL for very large concurrent use
- Scanned (image-only) PDFs can't be imported without OCR

Detailed behaviour of each feature is documented in [`docs/DEVELOPMENT_NOTES.md`](docs/DEVELOPMENT_NOTES.md).
