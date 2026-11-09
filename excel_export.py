"""
Excel (.xlsx) export helpers, built with openpyxl. Plain data dumps, no
formulas — no recalculation step needed, the workbook is complete as saved.
"""
import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment

HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF")
HEADER_FILL = PatternFill(start_color="0A1628", end_color="0A1628", fill_type="solid")
BODY_FONT = Font(name="Arial")


def _style_header_row(ws, row_idx, num_cols):
    for col in range(1, num_cols + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center")


def _autosize_columns(ws, widths):
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = width


def _to_bytes(wb):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def build_attendance_workbook(exam, attendance_rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"

    ws.append([f"Attendance Register — {exam.title} ({exam.subject})"])
    ws["A1"].font = Font(name="Arial", bold=True, size=13)
    ws.append([])

    headers = ["S/N", "Name", "Registration No.", "Checked In At"]
    ws.append(headers)
    _style_header_row(ws, ws.max_row, len(headers))

    for i, row in enumerate(attendance_rows, start=1):
        ws.append([
            i, row.name, row.reg_no,
            row.checked_in_at.strftime("%Y-%m-%d %H:%M:%S") if row.checked_in_at else "",
        ])

    for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
        for cell in row:
            cell.font = BODY_FONT

    _autosize_columns(ws, [6, 28, 20, 22])
    return _to_bytes(wb)


def build_results_workbook(exam, attempts):
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"

    ws.append([f"Results — {exam.title} ({exam.subject})"])
    ws["A1"].font = Font(name="Arial", bold=True, size=13)
    ws.append([f"Pass mark: {exam.pass_mark}%"])
    ws.append([])

    headers = ["S/N", "Name", "Registration No.", "Score", "Total Marks", "Outcome", "Status", "Flags", "Retake Status", "Submitted At"]
    ws.append(headers)
    _style_header_row(ws, ws.max_row, len(headers))

    for i, a in enumerate(attempts, start=1):
        outcome = ""
        if a.score is not None:
            outcome = "PASS" if a.score >= exam.pass_mark else "FAIL"
        ws.append([
            i, a.user.name, a.user.reg_no,
            a.raw_score if a.raw_score is not None else "",
            a.total_marks_snapshot if a.total_marks_snapshot is not None else exam.total_marks(),
            outcome,
            a.status.replace("_", " ").title(),
            len(a.violations),
            "Superseded (retake given)" if a.retake_granted else "Current",
            a.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if a.submitted_at else "",
        ])

    for row in ws.iter_rows(min_row=4, max_row=ws.max_row):
        for cell in row:
            cell.font = BODY_FONT

    _autosize_columns(ws, [6, 28, 20, 10, 12, 10, 16, 8, 20, 22])
    return _to_bytes(wb)


def build_credentials_workbook(accounts):
    wb = Workbook()
    ws = wb.active
    ws.title = "Student Logins"

    ws.append(["Generated Student Login Credentials"])
    ws["A1"].font = Font(name="Arial", bold=True, size=13)
    ws.append(["Keep this file secure — it contains plaintext passwords for first login."])
    ws.append([])

    headers = ["S/N", "Name", "Registration No. (Username)", "Password"]
    ws.append(headers)
    _style_header_row(ws, ws.max_row, len(headers))

    for i, acc in enumerate(accounts, start=1):
        ws.append([i, acc["name"], acc["reg_no"], acc["password"]])

    for row in ws.iter_rows(min_row=4, max_row=ws.max_row):
        for cell in row:
            cell.font = BODY_FONT

    _autosize_columns(ws, [6, 28, 26, 16])
    return _to_bytes(wb)
