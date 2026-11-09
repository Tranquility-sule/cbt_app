def compute_score(attempt):
    """
    Returns (earned_marks, total_marks, percentage) for a submitted/
    auto-submitted attempt. Unanswered questions count as wrong (0 marks).
    percentage is kept around purely for internal pass/fail comparison
    against Exam.pass_mark — the score shown to people is raw marks
    (earned/total), not a percentage.
    """
    exam = attempt.exam
    total_marks = exam.total_marks()
    if total_marks == 0:
        return 0.0, 0.0, 0.0

    answered = {a.question_id: a.selected_option_id for a in attempt.answers}

    earned = 0.0
    for question in exam.questions:
        selected_id = answered.get(question.id)
        if selected_id is None:
            continue
        correct_option = next((o for o in question.options if o.is_correct), None)
        if correct_option and correct_option.id == selected_id:
            earned += question.marks

    percentage = round((earned / total_marks) * 100, 2)
    return earned, total_marks, percentage


def grade_attempt(attempt):
    """Backward-compatible helper — returns just the percentage."""
    _, _, percentage = compute_score(attempt)
    return percentage
