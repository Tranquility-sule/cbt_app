"""
Simple rule-based FAQ matching — no external AI/API involved. Deliberately
scoped to login/account/navigation help, not exam content, and the widget
that uses this is never shown on the exam-taking page itself.
"""

FAQ_ENTRIES = [
    {
        "keywords": ["log in", "login", "sign in", "signin", "can't login", "cannot login"],
        "answer": "To log in, use the Registration Number and Password given to you by your "
                  "admin or teacher — enter them on the login page and click Sign In.",
    },
    {
        "keywords": ["forgot password", "forgot my password", "lost password", "wrong password",
                     "reset password", "password not working", "password doesn't work"],
        "answer": "You can't reset your own password — ask your admin or teacher to reset it "
                  "for you from the Students page. You'll be asked to set a new password the "
                  "next time you log in.",
    },
    {
        "keywords": ["change password", "update password", "new password"],
        "answer": "Click \"Change Password\" in the top navigation menu once you're logged in.",
    },
    {
        "keywords": ["start exam", "begin exam", "how do i take", "how to take exam", "take my exam"],
        "answer": "Go to the Exams page, find your subject's card, and click \"Start [Subject] Exam\". "
                  "If the button isn't there, the exam may not be open yet — check with your teacher.",
    },
    {
        "keywords": ["timer", "time up", "time expired", "ran out of time", "time out"],
        "answer": "If your exam time runs out, it's automatically submitted with whatever answers "
                  "were saved — you don't need to do anything.",
    },
    {
        "keywords": ["internet", "disconnect", "network", "lost connection", "wifi", "offline"],
        "answer": "If your internet drops during an exam, don't worry — your answers are saved as "
                  "you select them. Just reconnect and continue; your progress won't be lost.",
    },
    {
        "keywords": ["can't see exam", "cannot see exam", "no exam", "exam not showing", "missing exam"],
        "answer": "If you don't see an exam listed, it may not be open yet, or you may not be "
                  "registered for it. Contact your admin or teacher to check.",
    },
    {
        "keywords": ["result", "score", "my score", "check result", "see result"],
        "answer": "Your result appears on the Exams page once your teacher publishes it. If it's "
                  "not showing yet, results just haven't been released for that exam.",
    },
    {
        "keywords": ["profile photo", "upload photo", "picture", "avatar"],
        "answer": "Click your name/avatar in the top navigation, then \"Upload Photo\". "
                  "It's completely optional — you don't need one to use the system.",
    },
    {
        "keywords": ["contact", "help", "support", "who do i ask", "human", "real person"],
        "answer": "For anything I can't help with, contact your class teacher or admin directly — "
                  "they can look up your account and fix most issues.",
    },
]

FALLBACK_ANSWER = (
    "I'm not sure about that one — try rephrasing, or contact your admin/teacher directly "
    "for anything account or exam-specific I can't help with."
)


def match_faq(message):
    message = (message or "").lower()
    best_entry = None
    best_score = 0

    for entry in FAQ_ENTRIES:
        score = sum(1 for kw in entry["keywords"] if kw in message)
        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry:
        return best_entry["answer"]
    return FALLBACK_ANSWER
