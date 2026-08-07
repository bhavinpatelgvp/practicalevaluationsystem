from io import BytesIO
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session
from models.schema import Assignment, Evaluation, Student, Submission


def marks_dataframe(db: Session) -> pd.DataFrame:
    statement = (
        select(Student.enrollment_no, Student.user_id, Assignment.status, Submission.github_url, Evaluation.total_marks, Evaluation.grade)
        .select_from(Student)
        .join(Assignment, Assignment.student_id == Student.id)
        .join(Submission, Submission.assignment_id == Assignment.id, isouter=True)
        .join(Evaluation, Evaluation.submission_id == Submission.id, isouter=True)
    )
    rows = db.execute(statement).all()
    return pd.DataFrame(rows, columns=["Enrollment", "User ID", "Status", "GitHub URL", "Marks", "Grade"])


def excel_report(db: Session) -> BytesIO:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        marks_dataframe(db).to_excel(writer, index=False, sheet_name="Marks")
    output.seek(0)
    return output


def pdf_report(db: Session) -> BytesIO:
    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4)
    frame = marks_dataframe(db).fillna("").astype(str)
    table = Table([list(frame.columns)] + frame.values.tolist(), repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    document.build([table]); output.seek(0)
    return output
