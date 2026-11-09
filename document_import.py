"""
Parses objective-question documents (Word .docx or PDF) into structured
question/option data, so a teacher can upload an existing past-questions
file instead of retyping everything.

The parser is heuristic, not a guarantee — it's designed to feed a
preview/confirm screen (see routes/teacher.py: import_document /
confirm_document_import), never to write straight to the database. A
human always confirms the detected correct answer before anything is
saved.
"""
import re

Q_NUMBER_RE = re.compile(r"^\s*(\d{1,3})[\.\)]\s+(.*)")
OPTION_RE = re.compile(r"^\s*([A-Ea-e])[\.\)]\s+(.*)")
ANSWER_RE = re.compile(r"^\s*(answer|ans|correct)\s*[:\-]?\s*([A-Ea-e])\b", re.IGNORECASE)


def parse_lines(lines, bold_flags=None):
    questions = []
    current = None

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line:
            continue
        bold = bold_flags[idx] if bold_flags else False

        m_ans = ANSWER_RE.match(line)
        if m_ans and current:
            current["detected_correct"] = m_ans.group(2).upper()
            continue

        m_opt = OPTION_RE.match(line)
        if m_opt and current:
            letter = m_opt.group(1).upper()
            text = m_opt.group(2).strip()
            current["options"].append({"letter": letter, "text": text, "bold": bold})
            if bold and not current["detected_correct"]:
                current["detected_correct"] = letter
            continue

        m_q = Q_NUMBER_RE.match(line)
        if m_q:
            if current and current["options"]:
                questions.append(current)
            current = {"text": m_q.group(2).strip(), "options": [], "detected_correct": None}
            continue

        if current:
            if not current["options"]:
                current["text"] += " " + line
            else:
                current["options"][-1]["text"] += " " + line

    if current and current["options"]:
        questions.append(current)

    return [q for q in questions if len(q["options"]) >= 2]


def extract_docx(file_stream):
    from docx import Document

    doc = Document(file_stream)
    lines = []
    bold_flags = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        lines.append(text)
        runs_with_text = [r for r in para.runs if r.text.strip()]
        is_bold = bool(runs_with_text) and all(r.bold for r in runs_with_text)
        bold_flags.append(is_bold)
    return lines, bold_flags


def extract_pdf(file_stream):
    import pdfplumber

    lines = []
    with pdfplumber.open(file_stream) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                lines.append(line)
    return lines, None


def parse_uploaded_file(file_storage):
    filename = (file_storage.filename or "").lower()

    if filename.endswith(".docx"):
        lines, bold_flags = extract_docx(file_storage)
    elif filename.endswith(".pdf"):
        lines, bold_flags = extract_pdf(file_storage)
    else:
        return None, "Please upload a .docx or .pdf file."

    if not lines:
        return None, "No readable text found in that file. If it's a scanned/image-based PDF, text extraction won't work — try a text-based file instead."

    questions = parse_lines(lines, bold_flags)

    if not questions:
        return None, (
            "Couldn't detect any questions in the expected format. Questions should "
            "look like: '1. Question text' followed by 'A. option', 'B. option', etc., "
            "one per line."
        )

    return questions, None
