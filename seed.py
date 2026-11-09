"""
Run once after first setup to create demo accounts and a sample exam:
    python seed.py
"""
from app import create_app
from models import db, School, User, Exam, Question, Option

app = create_app()

with app.app_context():
    db.create_all()

    if User.query.filter_by(reg_no="ADMIN001").first():
        print("Seed data already exists. Skipping.")
    else:
        school = School(name="Demo Secondary School")
        db.session.add(school)
        db.session.flush()

        admin = User(name="Admin User", reg_no="ADMIN001", role="admin", school_id=school.id, must_change_password=False)
        admin.set_password("admin123")

        teacher = User(name="Mrs. Aisha Bello", reg_no="TCH001", role="teacher", school_id=school.id, must_change_password=False)
        teacher.set_password("teacher123")

        student = User(name="Test Student", reg_no="STU001", role="student", school_id=school.id, must_change_password=False)
        student.set_password("student123")

        db.session.add_all([admin, teacher, student])
        db.session.flush()

        exam = Exam(
            title="Basic Science - First Term Test",
            subject="Basic Science",
            class_level="SS3",
            duration_minutes=20,
            shuffle_questions=True,
            shuffle_options=True,
            pass_mark=50,
            locked=False,
            created_by=teacher.id,
        )
        db.session.add(exam)
        db.session.flush()

        questions_data = [
            ("The process by which plants make their own food is called ____.",
             ["Photosynthesis", "Respiration", "Digestion", "Excretion"], 0),
            ("Which of these is NOT a state of matter?",
             ["Solid", "Liquid", "Gas", "Energy"], 3),
            ("The powerhouse of the cell is the ____.",
             ["Nucleus", "Mitochondria", "Ribosome", "Cell wall"], 1),
        ]

        for i, (text, options, correct_idx) in enumerate(questions_data):
            q = Question(exam_id=exam.id, text=text, marks=1.0, order_index=i)
            db.session.add(q)
            db.session.flush()
            for j, opt_text in enumerate(options):
                db.session.add(Option(
                    question_id=q.id, text=opt_text,
                    is_correct=(j == correct_idx), order_index=j,
                ))

        db.session.commit()
        print("Seed data created:")
        print("  Admin    -> reg_no: ADMIN001   password: admin123")
        print("  Teacher  -> reg_no: TCH001      password: teacher123")
        print("  Student  -> reg_no: STU001      password: student123")
