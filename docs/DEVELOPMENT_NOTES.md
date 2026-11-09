# School CBT — Python/Flask Computer-Based Testing App

A from-scratch CBT system built with Flask, SQLAlchemy, and vanilla JS.
Built to handle the four hard parts of exam-hall software: a server-authoritative
timer, per-student question/option randomization, offline-resilient answer
saving, and a teacher results dashboard.

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python seed.py                  # creates demo accounts + a sample exam
python app.py                   # runs on http://localhost:5000
```

Demo logins (created by `seed.py`):

| Role    | Reg No   | Password    |
|---------|----------|-------------|
| Admin   | ADMIN001 | admin123    |
| Teacher | TCH001   | teacher123  |
| Student | STU001   | student123  |

## How the hard parts are handled

**Timer** — `ExamAttempt.started_at` is set server-side when the exam begins.
Every page load, every answer save, and a periodic heartbeat poll all check
`deadline = started_at + duration` against the server clock, not the browser's.
A background sweeper (`sweeper.py`, via APScheduler) also auto-submits any
attempt past its deadline even if the student's device goes fully offline and
never sends another request.

**Randomization** — `shuffle.py` uses `random.Random(seed)` seeded on the
attempt ID, so a student's question/option order is stable across page
refreshes but different from the student next to them.

**Offline resilience** — `templates/take_exam.html` caches every answer in
`localStorage` immediately, then POSTs it to `/attempt/<id>/answer`, which is
an idempotent upsert (safe to retry). If a save fails, it retries with
exponential backoff and shows a "Reconnecting..." indicator. On page load,
any locally cached answer not yet confirmed by the server gets re-sent. For a
real exam hall, run the Flask server on a local machine on the same LAN/Wi-Fi
as the exam PCs — no internet dependency during the exam itself.

**Results dashboard** — auto-grading happens at submit time (`grading.py`).
Teachers get average/highest/lowest/pass-fail stats, a per-question "% wrong"
breakdown to flag bad questions, and CSV export
(`/teacher/exams/<id>/export.csv`).

## Project structure

```
app.py              # app factory, blueprint registration, sweeper startup
config.py           # settings (DB URI, secret key, sweep interval)
models.py           # School, User, Exam, Question, Option, ExamAttempt, Answer
shuffle.py           # deterministic per-attempt question/option ordering
grading.py           # auto-grading
sweeper.py           # background job to auto-submit expired attempts
seed.py              # demo data
routes/
  auth.py            # login/logout
  exam.py            # exam-taking flow (the timer/autosave core)
  teacher.py          # exam CRUD + results dashboard + CSV export
templates/           # Jinja2 templates
static/css/style.css # styling
```

## Concurrent logins, attendance, and admin downloads

**Multiple students logging in at the same time** already works with no
extra setup — every `User` has a unique `reg_no`, and Flask sessions are
per-browser-cookie, so 30 students on 30 different PCs are always
independent sessions. What was missing was an easy way to *create* that many
unique accounts, which is what bulk import solves:

- **Admin → "Bulk Add Students"** (`/admin/students/bulk`): upload a CSV with
  a `name` column (or a plain `.txt`, one name per line). Each student gets
  a sequential reg_no (e.g. `STU002`, `STU003`, ...) and a random 8-character
  password. An Excel file of the generated logins downloads immediately —
  this is the file you print/distribute before exam day.

- **Attendance** is recorded automatically the moment a student clicks
  "Start Exam" (not at login — login alone doesn't mean they sat the exam).
  Teachers/admins can view it live at `/admin/exams/<id>/attendance` or
  download it as Excel from the results page.

- **Results download**: the teacher results page now has both a CSV export
  and a formatted Excel export (`/teacher/exams/<id>/export.xlsx`), available
  to both teacher and admin accounts, listing name, reg_no, score, pass/fail
  outcome, and submission time.

## Password lifecycle

- Every account has a `must_change_password` flag. **Bulk-created student
  accounts start with this set to `True`** — on their very first login
  they're forced to `/change-password` before they can reach exams, even if
  they try to jump straight to a bookmarked URL (enforced app-wide, not just
  on the login redirect).
- Once a student sets their own password, the flag clears and they log in
  normally from then on.
- **Admin → "Students"** lists every student account with a password-status
  column and a "Reset Password" button. Resetting immediately invalidates
  the old password, generates a new random one (shown once, in a flash
  message — copy it immediately, it isn't stored anywhere retrievable), and
  re-sets `must_change_password` so the student is walked through setting
  their own password again on next login.
- Any logged-in user (student, teacher, or admin) can also change their own
  password voluntarily via the "Change Password" nav link.
- ## Updating without losing data

Whenever an update adds a new field (like `profile_photo` or `class_level`
did), your existing `cbt.db` won't have that column yet, and you'll see an
error like `no such column: users.profile_photo`. **Don't delete `cbt.db`
to fix this** — run the migration script instead:

```bash
python migrate.py
```

It compares what `models.py` expects against your actual database file and
adds only the missing columns, without touching any existing students,
exams, attendance, or results. Safe to run anytime, including when nothing
changed (it'll just say the schema is already up to date). This replaces
the old advice of deleting `cbt.db` and re-seeding — only do that if you
genuinely want to wipe everything and start over.

## Design system

The interface uses a deep navy + muted brass palette (`static/css/style.css`)
intended to read as "official exam authority" rather than a generic admin
template — Source Serif 4 for headings, Inter for body/forms, JetBrains Mono
for registration numbers, passwords, and the exam timer. A circular seal
mark (`templates/_seal.html`) is the recurring signature element: small in
the header, large on the login screen and results page. Status badges
(Pass/Fail, Submitted/Auto-submitted, Active/Awaiting first login) use
consistent color coding throughout. The exam timer deliberately avoids
blinking/pulsing under time pressure — it shifts to a calm red tone at 60
seconds remaining instead, to avoid adding to exam stress.

## Subject dashboard, profile photos, and bulk questions

- **Student dashboard** (`/exams`) now shows a card grid per subject — subject
  name, exam title, optional class level (e.g. "SS2"), duration, question
  count, and a status badge: **Active** (not started), **In Progress**
  (resume), or **Done** (view result). Matches the subject-card layout style
  common to CBT portals.
- **Profile photos are entirely optional.** Any user can go to the avatar/
  reg-no link in the nav → upload a PNG/JPG (max 3MB). Without one, a
  navy-and-gold initials circle is shown instead — nothing is required to
  use the system.
- **5 answer options (A–E)**, not just 4 — the question form and the CSV
  bulk-upload both support up to 5 options per question.
- **Bulk question upload via CSV** — on the exam editor page
  (`/teacher/exams/<id>`), teachers can upload a CSV instead of adding
  questions one at a time. Required columns: `question, option_a, option_b,
  correct` (plus optional `option_c`, `option_d`, `option_e`, `marks`).
  `correct` is the letter of the right answer (A–E).

## Importing questions from Word/PDF

On the exam editor page, "Import from Document" lets a teacher upload a
`.docx` or `.pdf` of existing objective questions instead of retyping them.
Expected format:

```
1. What is the capital of Nigeria?
A. Lagos
B. Abuja
C. Kano
D. Ibadan
Answer: B
```

Numbering can be "1." or "1)"; options can be "A." or "A)". The `Answer:`
line is optional — for `.docx` files, a **bolded** option is also read as
the correct answer if no Answer line is present (a common convention in
existing past-questions documents).

**Nothing is saved automatically.** Upload → a preview screen shows every
detected question with its options and the detected correct answer as a
pre-selected radio button. Any question where no answer could be detected
is flagged in red and must be manually resolved before import. Uncheck a
question to skip it. Only on clicking "Confirm & Import" does anything hit
the database. This is deliberate — automatic parsing of unstructured
documents will occasionally mis-detect something, and a wrong answer key
silently entering an exam is worse than a few minutes of review.

Limitations: scanned/image-based PDFs won't work (no text layer to read —
you'd need to OCR it first). Questions split across a table or unusual
layout may not parse correctly. Marks are set to 1 per imported question
(edit them individually afterward if needed).

## Score display

Scores now show as raw marks — "23 / 40" — instead of a percentage,
everywhere: the student results page, the teacher results dashboard
(summary stats and per-student table), and both the CSV and Excel exports.
Pass/Fail is still determined internally by comparing the percentage
against the exam's pass mark, but that percentage number itself is never
shown — only the Pass/Fail label. Existing attempts from before this
update won't have a raw score recorded (they'll show blank) since it's
computed at submission time; only new submissions get it. Run
`python migrate.py` after updating — this adds two new columns
(`raw_score`, `total_marks_snapshot`) to the existing `exam_attempts`
table without touching any data.

## Exam integrity monitoring

The exam-taking page now detects and logs (never auto-punishes) suspected
integrity issues:
- **Tab switches** and **window minimizing/losing focus** (via the
  browser's visibility/blur events)
- **Copy, cut, and paste attempts** inside the exam — blocked outright,
  and logged
- **Right-click** inside the exam — blocked and logged

Every event is timestamped and tied to the specific attempt. Teachers see
a **"Flags"** column on the results page — hover over it for a breakdown
by type (e.g. "tab_switch: 3, copy_attempt: 1") — and the same column is
included in both the CSV and Excel exports.

**This is informational only — nothing here auto-submits the exam or
penalizes the student automatically.** That's deliberate: false positives
happen (an accidental alt-tab, a phone call), so the decision of what to
do with a flagged attempt stays with the teacher.

**Real limitation, worth knowing:** none of this is bulletproof. A
determined student can still screenshot the screen, photograph it with a
phone, or bypass the JS restrictions using browser dev tools. This raises
the bar against casual cheating (alt-tabbing to search something,
copy-pasting into WhatsApp) — it is not a full lockdown/proctoring
solution. Run `python migrate.py` after updating; this adds the new
`exam_violations` table without touching existing data.

## Support chatbot

A floating chat widget (bottom-right, on every page except the actual
exam-taking screen) answers common questions — login help, forgotten
passwords, how to start an exam, what happens if the internet drops
mid-exam, checking results, and so on. It's rule-based keyword matching
(`faq_data.py`), not an AI API — no cost, nothing to keep secure, and
nothing that could leak exam content. It works even for someone not
logged in yet, since "I forgot my password" is exactly a login-page
problem. To add or edit answers, just edit the `FAQ_ENTRIES` list in
`faq_data.py` — each entry is a list of trigger keywords and one answer.

It's deliberately **not available on the exam-taking page itself** — kept
separate from anything that could look like external help during a live
exam.

## Locking exams

Every exam now has a Lock/Unlock toggle on the Teacher Dashboard. **New
exams are locked by default** — students see a "Locked by teacher" badge
instead of a Start button until a teacher explicitly clicks "Unlock for
Students." This is the mechanism for controlling exactly which exam
students can start at any given moment (e.g. unlocking only Geography
while Mathematics, Computer Science, and Social Studies stay locked).

Locking an exam only blocks *new* attempts — a student already in the
middle of that exam is never interrupted or kicked out if a teacher locks
it while they're still taking it.

**Note on existing exams from before this update**: they are not
retroactively locked — they keep behaving exactly as before (open unless
you explicitly lock them), since silently locking exams already in use
without a teacher's action would be disruptive. Only newly created exams
default to locked. Run `python migrate.py` after updating to add the new
`locked` column.

## Restricting exams to a department

Rather than relying on a registration-number prefix (fragile — nothing
actually enforces it), students now have a real **Department** field, and
exams have a **"Restrict to Department"** setting.

**Setting it up:**
1. Admin → Bulk Add Students → fill in the "Department" field (e.g.
   "Computer Science") before uploading that batch's name list. Every
   student created from that upload is tagged with that department.
2. Teacher → New Exam → "Restrict to Department" — enter the exact
   department name (not case-sensitive) to limit the exam to only those
   students, or leave it blank for an exam open to everyone.

**What this actually does:** a restricted exam doesn't just hide its Start
button from ineligible students — it's completely absent from their exam
list, and the server independently refuses to start an attempt for them
even if they somehow POST directly to the start URL (verified: zero
attempts get created, and the correct "restricted to X students" message
is shown). Hiding in the UI alone would not have been a real restriction.

Run `python migrate.py` after updating — this adds `department` to
`users` and `restricted_department` to `exams`, without touching existing
accounts (they'll simply have no department set, meaning they're
unaffected by any department-restricted exam until you assign one).

## Editing and deleting exams

**Editing exam details** (title, subject, duration, pass mark, class,
department restriction, shuffle settings) is available via "Edit Exam
Details" on the exam editor page. Important to understand: **renaming an
exam changes its title everywhere, including on results already
submitted under the old name** — the title isn't frozen at submission
time, so a student who took "Basic Science Test" last week will see the
new name if you rename it later. Duration/shuffle changes only affect
attempts started after the change; already-graded attempts are untouched.

**Deleting an exam** is blocked outright once any student has attempted
it — verified directly: attempting to delete an exam with an existing
attempt is refused with a clear explanation, and nothing is touched.
This is deliberate: an ExamAttempt's answers and a candidate's Attendance
record both point back to the exam, and deleting it out from under them
would break their results, exports, and attendance views. **Use "Lock"
instead** if you want to stop further attempts on an exam that already
has student data — deletion is only for exams with zero attempts (e.g. a
test exam you created by mistake), and correctly cascades to remove its
questions and options when it does go through.

## Bulk restart and permanent score deletion

On the exam Results page, alongside the per-student "Allow Retake" /
"Delete Score" actions, there are two class-wide buttons:

- **"Restart for All Students"** — grants a retake to every student who
  has finished the exam, in one click. Every existing score is preserved
  and stays visible in the table (marked "Superseded"), exactly like an
  individual retake — nothing is deleted. Use this after fixing a
  question so the whole class can redo it fairly.
- **"Delete All Scores"** — the destructive counterpart. Permanently
  erases every finished attempt's score, answers, and logged violations
  for this exam. **There is no undo and no backup of what's deleted.**
  Use "Restart for All Students" instead unless you genuinely want the
  old scores gone from the record entirely (e.g. a botched test run you
  don't want cluttering real results).

Both respect in-progress attempts — a student actively mid-exam is never
affected by either action, whether triggered individually or in bulk.

Tested directly before shipping: bulk-restarted two students (scores 1/1
and 0/1 both preserved and marked superseded, dashboards correctly
flipped back to "Active"), individually deleted one score (confirmed its
answers were cascade-deleted with no orphaned rows, other students'
attempts untouched), then bulk-deleted the rest (confirmed zero attempts
remained), and confirmed an in-progress attempt survives every one of
these operations untouched.

Run `python migrate.py` after updating.

## Handling 100+ students at once

I load-tested this directly — seeded 100 real student accounts and fired
truly simultaneous login+start-exam requests at the running server, both
before and after the changes described below.

**The good news, confirmed by testing:** even at 100 simultaneous starts,
there were zero errors and zero data corruption — every student got
their own correct, distinct exam attempt with no duplicates or lost
data. That held true throughout.

**The real limitation:** password verification is deliberately
CPU-intensive (by security design, to resist brute-forcing), so 100
logins landing in the same instant means real queueing while that work
happens. `python app.py` runs Flask's default single-threaded dev
server, meaning all of that work queues one request at a time.

**Two fixes applied:**
1. `app.py` now runs with `threaded=True`, and `python app.py` no longer
   serializes every request — but for a real exam with a meaningful
   number of students, use `python run_production.py` instead. It runs
   the same app through **waitress** (a real production WSGI server,
   16 threads) rather than Flask's dev server, which explicitly warns
   it isn't meant for this.
2. **SQLite WAL mode** is now enabled automatically on every connection —
   this is what actually matters for the *sustained* load throughout an
   exam (everyone's answers autosaving, heartbeat polling, submitting),
   not just the opening rush. It lets reads and writes coexist without
   blocking each other, which the default SQLite mode does not do well.

**What this means practically**: on real hardware with more than one CPU
core (any normal laptop), the queueing delay at login should be
meaningfully shorter than a single-core worst case, since password
verification parallelizes across cores once threading is actually in
use. I'd still recommend testing with a smaller real batch (say 20-30
accounts) on your actual machine before a big exam day, since exact
numbers depend on your hardware.

**Backup note**: since WAL mode keeps very recent writes in a separate
file until checkpointed, "Backup Database" now forces a checkpoint before
copying — verified directly that a student created moments before backup
is correctly included, not missing.

Run `python migrate.py` after updating (no schema change this time, so
it should report "already up to date" — just confirms nothing's stale).

## Known limitations / next steps

- Only MCQ/true-false question types are auto-graded; essay/short-answer
  would need manual marking UI.
- No password reset flow — an admin panel for resetting student passwords
  would be a natural next addition.
- `SECRET_KEY` and `DATABASE_URL` should be set via environment variables in
  production, not left as the defaults in `config.py`.
- For multi-exam-hall deployments (many PCs, one LAN server), consider
  switching from SQLite to PostgreSQL — SQLite can struggle with concurrent
  writes from 30+ students submitting/saving answers simultaneously.

## Teacher accounts and exam ownership

Admin → **Teachers** creates teacher accounts (TCH001, TCH002, ...), each with its own random
password and forced change on first login, plus reset-password and delete (blocked while the
teacher owns exams). A teacher only sees and can act on exams they created: dashboard, editing,
questions, imports, results, exports, retakes, score deletion and attendance. Anyone else gets a
404, so they can't tell the exam exists. Admins see and manage all exams. Exams with no recorded
creator are visible to admins only. The rule lives in `access.py` (`owned_exam_or_404`).

### Teacher limit and hand-over
`TEACHER_LIMIT` (default 15, override with the environment variable of the same name) caps teacher
accounts. **Hand Over** (Admin → Teachers) moves a finished teacher's exams to the admin (results
untouched), renames the account to the new person, removes the photo and issues a fresh password
with forced change on first login.

## Teacher limit and account handover

Teacher accounts are capped at 15 by default (`MAX_TEACHERS` in `config.py`, or set the
`MAX_TEACHERS` environment variable). At the limit, Admin → Teachers refuses to create another.
**Hand Over** reuses a finished teacher's account for a new person: the old teacher's exams
move to the admin (results are kept), the account is renamed, and a new password is issued
with a forced change on first login. The old password stops working immediately.
