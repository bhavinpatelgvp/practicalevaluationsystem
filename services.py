from datetime import date, datetime, time, timedelta
from io import BytesIO
import re
import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from auth import hash_password
from models import (
    Assignment,
    AuditLog,
    Department,
    Evaluation,
    FacultySubject,
    Practical,
    Role,
    Student,
    Subject,
    Submission,
    User,
)

GITHUB_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?$")
VALID_GRADES = {"A", "B", "C", "D", "E", "F"}
FACULTY_ROLE = "Faculty"


def audit(db: Session, actor_id: int | None, action: str, entity: str, entity_id: int | None = None, details: str = "") -> None:
    db.add(AuditLog(actor_id=actor_id, action=action, entity=entity, entity_id=entity_id, details=details))


def assign_practical(db: Session, practical: Practical, actor_id: int, student_ids: list[int] | None = None) -> int:
    """Create missing assignments for the given students (or every enrolled student)."""
    statement = select(Student)
    if student_ids:
        statement = statement.where(Student.id.in_(student_ids))
    students = db.scalars(statement).all()
    existing = set(db.scalars(select(Assignment.student_id).where(Assignment.practical_id == practical.id)))
    created = 0
    deadline = (
        datetime.combine(practical.submission_date, time.max)
        if practical.submission_date
        else datetime.utcnow() + timedelta(days=practical.submission_days)
    )
    for student in students:
        if student.id not in existing:
            db.add(Assignment(practical_id=practical.id, student_id=student.id, deadline=deadline))
            created += 1
    audit(db, actor_id, "ASSIGN_PRACTICAL", "Practical", practical.id, f"Assigned to {created} students")
    db.commit()
    return created


def save_submission(db: Session, assignment_id: int, github_url: str, actor_id: int, **fields) -> Submission:
    if not GITHUB_RE.match(github_url.strip()):
        raise ValueError("Enter a valid public GitHub repository URL.")
    assignment = db.scalar(select(Assignment).options(joinedload(Assignment.submission)).where(Assignment.id == assignment_id))
    if not assignment:
        raise ValueError("Assignment not found.")
    if assignment.submission is None:
        submission = Submission(assignment=assignment, github_url=github_url.strip(), is_late=datetime.utcnow() > assignment.deadline, **fields)
        db.add(submission)
    else:
        submission = assignment.submission
        if datetime.utcnow() > assignment.deadline:
            raise ValueError("The submission deadline has passed.")
        submission.github_url = github_url.strip()
        for key, value in fields.items():
            setattr(submission, key, value)
    assignment.status = "Late" if submission.is_late else "Submitted"
    audit(db, actor_id, "SUBMIT_REPOSITORY", "Assignment", assignment.id, submission.github_url)
    db.commit()
    db.refresh(submission)
    return submission


def grade_submission(db: Session, submission_id: int, evaluator_id: int, grade: str, remarks: str, suggestions: str) -> Evaluation:
    grade = grade.strip().upper()
    if grade not in VALID_GRADES:
        raise ValueError("Grade must be one of A, B, C, D, E, or F.")
    submission = db.get(Submission, submission_id)
    if not submission:
        raise ValueError("Submission not found.")
    evaluation = submission.evaluation or Evaluation(submission_id=submission.id)
    db.add(evaluation)
    evaluation.grade = grade
    evaluation.evaluator_id = evaluator_id
    evaluation.remarks = remarks
    evaluation.suggestions = suggestions
    evaluation.published = True
    submission.assignment.status = "Evaluated"
    audit(db, evaluator_id, "PUBLISH_EVALUATION", "Submission", submission.id, grade)
    db.commit()
    db.refresh(evaluation)
    return evaluation


def dashboard_counts(db: Session) -> dict[str, int | float]:
    counts = {
        "students": db.scalar(select(func.count(Student.id))) or 0,
        "assignments": db.scalar(select(func.count(Assignment.id))) or 0,
        "submissions": db.scalar(select(func.count(Submission.id))) or 0,
        "evaluated": db.scalar(select(func.count(Evaluation.id))) or 0,
    }
    counts["pending"] = counts["assignments"] - counts["submissions"]
    counts["late"] = db.scalar(select(func.count(Assignment.id)).where(Assignment.status == "Late")) or 0
    counts["average"] = float(db.scalar(select(func.avg(Evaluation.total_marks))) or 0)
    return counts


def ensure_role(db: Session, role_name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        role = Role(name=role_name)
        db.add(role)
        db.flush()
    return role


def build_bulk_import_template(user_type: str) -> bytes:
    """Return an Excel template for the requested bulk-import type."""
    templates = {
        "student": pd.DataFrame([
            {"Enrollment No": "E1001", "Roll No": "01", "Name": "Student Name", "Email": "student@example.com", "Mobile": "9876543210", "Course": "MCA", "Semester": "3", "Division": "A", "Batch": "B1"}
        ]),
        "faculty": pd.DataFrame([
            {"Faculty ID": "F1001", "Name": "Faculty Name", "Email": "faculty@example.com", "Mobile": "9876543210", "Department": "Computer Science", "Designation": "Assistant Professor"}
        ]),
        "admin": pd.DataFrame([
            {"Employee ID": "A1001", "Name": "Admin Name", "Email": "admin@example.com", "Mobile": "9876543210", "Role": "Administrator"}
        ]),
    }
    if user_type not in templates:
        raise ValueError("Unsupported import type")
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        templates[user_type].to_excel(writer, index=False, sheet_name="Import")
    return workbook.getvalue()


def validate_bulk_user_import(rows: pd.DataFrame, user_type: str, db: Session) -> list[dict[str, object]]:
    """Validate rows for bulk user import and return a preview-style list of records."""
    if user_type not in {"student", "faculty", "admin"}:
        raise ValueError("Unsupported import type")

    required_columns = {
        "student": ["Enrollment No", "Name", "Email", "Mobile", "Course", "Semester", "Division", "Batch"],
        "faculty": ["Faculty ID", "Name", "Email", "Mobile", "Department", "Designation"],
        "admin": ["Employee ID", "Name", "Email", "Mobile", "Role"],
    }[user_type]

    missing_columns = [column for column in required_columns if column not in rows.columns]
    if missing_columns:
        raise ValueError(f"Missing columns: {', '.join(missing_columns)}")

    preview: list[dict[str, object]] = []
    seen_enrollment: set[str] = set()
    seen_email: set[str] = set()
    seen_employee: set[str] = set()

    for index, row in rows.fillna("").iterrows():
        record: dict[str, object] = {
            "row": index + 2,
            "status": "Ready",
            "reason": "Ready to import",
            "ready": True,
            "duplicate": False,
        }
        values = {key: str(value).strip() if isinstance(value, str) else str(value).strip() for key, value in row.items()}

        if not any(values.values()):
            record.update({"status": "Error", "reason": "Empty row", "ready": False})
            preview.append(record)
            continue

        required_field = None
        if user_type == "student":
            required_field = values.get("Enrollment No") or values.get("Name") or values.get("Email")
        elif user_type == "faculty":
            required_field = values.get("Faculty ID") or values.get("Name") or values.get("Email")
        else:
            required_field = values.get("Employee ID") or values.get("Name") or values.get("Email")

        if not required_field:
            record.update({"status": "Error", "reason": "Missing mandatory fields", "ready": False})
            preview.append(record)
            continue

        if user_type == "student":
            enrollment = values.get("Enrollment No", "")
            email = values.get("Email", "")
            if not enrollment:
                record.update({"status": "Error", "reason": "Missing Enrollment No", "ready": False})
            elif enrollment in seen_enrollment or db.scalar(select(User).where(User.username == enrollment)) is not None:
                record.update({"status": "Warning", "reason": "Duplicate Enrollment No", "ready": False, "duplicate": True})
            else:
                seen_enrollment.add(enrollment)
            if email in seen_email or db.scalar(select(User).where(User.email == email)) is not None:
                record.update({"status": "Warning", "reason": "Duplicate Email", "ready": False, "duplicate": True})
            else:
                seen_email.add(email)
        elif user_type == "faculty":
            faculty_id = values.get("Faculty ID", "")
            email = values.get("Email", "")
            if not faculty_id:
                record.update({"status": "Error", "reason": "Missing Faculty ID", "ready": False})
            elif faculty_id in seen_employee or db.scalar(select(User).where(User.username == faculty_id)) is not None:
                record.update({"status": "Warning", "reason": "Duplicate Faculty ID", "ready": False, "duplicate": True})
            else:
                seen_employee.add(faculty_id)
            if email in seen_email or db.scalar(select(User).where(User.email == email)) is not None:
                record.update({"status": "Warning", "reason": "Duplicate Email", "ready": False, "duplicate": True})
            else:
                seen_email.add(email)
        else:
            employee_id = values.get("Employee ID", "")
            email = values.get("Email", "")
            if not employee_id:
                record.update({"status": "Error", "reason": "Missing Employee ID", "ready": False})
            elif employee_id in seen_employee or db.scalar(select(User).where(User.username == employee_id)) is not None:
                record.update({"status": "Warning", "reason": "Duplicate Employee ID", "ready": False, "duplicate": True})
            else:
                seen_employee.add(employee_id)
            if email in seen_email or db.scalar(select(User).where(User.email == email)) is not None:
                record.update({"status": "Warning", "reason": "Duplicate Email", "ready": False, "duplicate": True})
            else:
                seen_email.add(email)

        preview.append(record)

    return preview


def import_bulk_users_from_dataframe(rows: pd.DataFrame, user_type: str, db: Session, actor_id: int) -> dict[str, int]:
    """Create users from a validated import sheet. Returns a summary dictionary."""
    preview = validate_bulk_user_import(rows, user_type, db)
    summary = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0}
    role_name = {"student": "Student", "faculty": "Faculty", "admin": "Administrator"}[user_type]
    role = ensure_role(db, role_name)
    for index, row in rows.fillna("").iterrows():
        if not preview[index].get("ready", False):
            summary["skipped"] += 1
            continue
        values = {key: str(value).strip() if isinstance(value, str) else str(value).strip() for key, value in row.items()}
        try:
            username = values.get("Enrollment No") or values.get("Faculty ID") or values.get("Employee ID") or values.get("Email")
            email = values.get("Email", "")
            full_name = values.get("Name", "")
            password = f"Temp{(index + 1) * 7}"
            if not username or not email or not full_name:
                summary["failed"] += 1
                continue
            existing = db.scalar(select(User).where((User.username == username) | (User.email == email)))
            if existing:
                summary["skipped"] += 1
                continue
            user = User(
                username=username,
                full_name=full_name,
                email=email,
                password_hash=hash_password(password),
                role_id=role.id,
                is_active=True,
            )
            db.add(user)
            db.flush()
            if user_type == "student":
                enrollment_no = values.get("Enrollment No", "")
                semester = int(values.get("Semester", 1) or 1)
                student = Student(user_id=user.id, enrollment_no=enrollment_no, semester=semester, program=values.get("Course", "MCA"))
                db.add(student)
            audit(db, actor_id, "BULK_IMPORT", "User", user.id, f"{user_type}:{username}")
            summary["imported"] += 1
        except Exception:
            db.rollback()
            summary["failed"] += 1
            break
    db.commit()
    return summary


def build_subject_import_template() -> bytes:
    """Return an Excel template for bulk subject import."""
    template = pd.DataFrame([
        {
            "Subject Code": "010101010101",
            "Subject Name": "Database Management Systems",
            "Semester": 3,
            "Course": "MCA",
            "Department": "Computer Science",
            "Credits": 4,
            "Subject Type": "Theory",
            "Status": "Active",
        }
    ])
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        template.to_excel(writer, index=False, sheet_name="Subjects")
    return workbook.getvalue()


def validate_subject_import(rows: pd.DataFrame, db: Session) -> list[dict[str, object]]:
    """Validate subject import rows and return preview-style records."""
    required_columns = ["Subject Code", "Subject Name", "Semester", "Course", "Department", "Credits", "Subject Type", "Status"]
    missing_columns = [column for column in required_columns if column not in rows.columns]
    if missing_columns:
        raise ValueError(f"Missing columns: {', '.join(missing_columns)}")

    preview: list[dict[str, object]] = []
    seen_codes: set[str] = set()
    seen_names: set[str] = set()
    department_lookup = {item.code.lower(): item.id for item in db.scalars(select(Department))}
    course_lookup = {item.name.lower(): item.id for item in []}

    for index, row in rows.fillna("").iterrows():
        values = {key: str(value).strip() if isinstance(value, str) else str(value).strip() for key, value in row.items()}
        record: dict[str, object] = {
            "row": index + 2,
            "subject_code": values.get("Subject Code", ""),
            "subject_name": values.get("Subject Name", ""),
            "semester": values.get("Semester", ""),
            "course": values.get("Course", ""),
            "department": values.get("Department", ""),
            "credits": values.get("Credits", ""),
            "subject_type": values.get("Subject Type", ""),
            "status": values.get("Status", ""),
            "validation_status": "Valid",
            "error_message": "",
            "ready": True,
        }
        if not any(values.values()):
            record.update({"validation_status": "Error", "error_message": "Empty row", "ready": False})
            preview.append(record)
            continue

        code = values.get("Subject Code", "")
        name = values.get("Subject Name", "")
        semester = values.get("Semester", "")
        course = values.get("Course", "")
        department = values.get("Department", "")
        credits = values.get("Credits", "")
        subject_type = values.get("Subject Type", "")
        status = values.get("Status", "")

        errors: list[str] = []
        if not code:
            errors.append("Subject Code is required")
        elif not re.fullmatch(r"\d{12}", code):
            errors.append("Subject Code must be exactly 12 numeric digits")
        elif code in seen_codes or db.scalar(select(Subject).where(Subject.code == code)) is not None:
            errors.append("Subject Code already exists")
        else:
            seen_codes.add(code)

        if not name:
            errors.append("Subject Name is required")
        elif len(name) > 200:
            errors.append("Subject Name exceeds 200 characters")
        elif name.lower() in seen_names or db.scalar(select(Subject).where(Subject.name == name)) is not None:
            errors.append("Subject Name already exists")
        else:
            seen_names.add(name.lower())

        try:
            semester_int = int(str(semester).strip())
        except ValueError:
            semester_int = None
            errors.append("Semester must be an integer")
        if semester_int is not None and not 1 <= semester_int <= 10:
            errors.append("Semester must be between 1 and 10")

        if not course:
            errors.append("Course is required")
        if not department:
            errors.append("Department is required")
        elif department.lower() not in department_lookup:
            errors.append("Department does not exist")

        if credits not in {"", None}:
            try:
                credits_value = float(str(credits).strip())
            except ValueError:
                credits_value = None
                errors.append("Credits must be numeric")
            if credits_value is not None and not 0 <= credits_value <= 20:
                errors.append("Credits must be between 0 and 20")

        if subject_type not in {"Theory", "Practical", "Theory + Practical", "Project", "Internship", "Elective"}:
            errors.append("Invalid Subject Type")

        if status not in {"Active", "Inactive"}:
            errors.append("Invalid Status")

        if errors:
            record.update({"validation_status": "Error", "error_message": "; ".join(errors), "ready": False})
        else:
            record.update({"validation_status": "Valid", "error_message": "", "ready": True})

        preview.append(record)

    return preview


def import_subjects_from_dataframe(rows: pd.DataFrame, db: Session, actor_id: int, mode: str = "insert") -> dict[str, int]:
    """Import validated subject rows using a transaction-safe workflow."""
    preview = validate_subject_import(rows, db)
    summary = {"imported": 0, "updated": 0, "skipped": 0, "failed": 0}
    try:
        with db.begin():
            for index, row in rows.fillna("").iterrows():
                record = preview[index]
                if not record.get("ready", False):
                    summary["skipped"] += 1
                    continue
                values = {key: str(value).strip() if isinstance(value, str) else str(value).strip() for key, value in row.items()}
                department = db.scalar(select(Department).where(Department.name == values.get("Department", "")))
                if not department:
                    summary["failed"] += 1
                    continue
                existing = db.scalar(select(Subject).where(Subject.code == values.get("Subject Code", "")))
                if existing:
                    if mode == "update":
                        existing.name = values.get("Subject Name", "")
                        existing.semester = int(values.get("Semester", 1))
                        existing.department_id = department.id
                        existing.credits = float(values.get("Credits", 0)) if values.get("Credits", "") not in {"", None} else None
                        existing.subject_type = values.get("Subject Type", "Theory")
                        existing.status = values.get("Status", "Active")
                        summary["updated"] += 1
                    else:
                        summary["skipped"] += 1
                        continue
                else:
                    db.add(
                        Subject(
                            code=values.get("Subject Code", ""),
                            name=values.get("Subject Name", ""),
                            semester=int(values.get("Semester", 1)),
                            department_id=department.id,
                            credits=float(values.get("Credits", 0)) if values.get("Credits", "") not in {"", None} else None,
                            subject_type=values.get("Subject Type", "Theory"),
                            status=values.get("Status", "Active"),
                        )
                    )
                    summary["imported"] += 1
                audit(db, actor_id, "BULK_IMPORT_SUBJECTS", "Subject", None, f"Imported {values.get('Subject Code', '')}")
            db.flush()
    except IntegrityError:
        db.rollback()
        summary["failed"] += 1
    return summary


# --------------------------------------------------------------------------
# Subject-wise faculty assignment
# --------------------------------------------------------------------------


def subjects_for_faculty(db: Session, faculty_id: int) -> list[Subject]:
    """Subjects explicitly assigned to a faculty member, ordered by code."""
    return list(
        db.scalars(
            select(Subject)
            .join(FacultySubject, FacultySubject.subject_id == Subject.id)
            .where(FacultySubject.faculty_id == faculty_id)
            .order_by(Subject.code)
        )
    )


def faculty_subject_ids(db: Session, faculty_id: int) -> set[int]:
    return {item[0] for item in db.execute(select(FacultySubject.subject_id).where(FacultySubject.faculty_id == faculty_id)).all()}


def assign_faculty_subjects(db: Session, faculty_id: int, subject_ids: list[int], actor_id: int) -> None:
    """Replace a faculty member's subject assignments with the given set (subject-wise Faculty)."""
    subject_ids = list(dict.fromkeys(subject_ids))  # de-duplicate, keep order
    current = faculty_subject_ids(db, faculty_id)
    to_add = [subject_id for subject_id in subject_ids if subject_id not in current]
    to_remove = [subject_id for subject_id in current if subject_id not in subject_ids]
    for subject_id in to_add:
        db.add(FacultySubject(faculty_id=faculty_id, subject_id=subject_id, assigned_by=actor_id))
    for subject_id in to_remove:
        link = db.scalar(
            select(FacultySubject).where(FacultySubject.faculty_id == faculty_id, FacultySubject.subject_id == subject_id)
        )
        if link:
            db.delete(link)
    if to_add or to_remove:
        audit(db, actor_id, "UPDATE_FACULTY_SUBJECTS", "User", faculty_id, f"Subjects: +{to_add} -{to_remove}")
        db.commit()


# --------------------------------------------------------------------------
# Practical management (faculty-facing, scoped to assigned subjects)
# --------------------------------------------------------------------------


def next_practical_number(db: Session, subject_id: int) -> int:
    current = db.scalar(
        select(func.max(Practical.practical_number)).where(Practical.subject_id == subject_id)
    )
    return (current or 0) + 1


def create_practical(
    db: Session,
    subject_id: int,
    title: str,
    description: str,
    grade: str,
    submission_date: date,
    creator_id: int,
    learning_outcome: str = "",
    difficulty: str = "Medium",
) -> Practical:
    grade = grade.strip().upper()
    if grade not in VALID_GRADES:
        raise ValueError("Grade must be one of A, B, C, D, E, or F.")
    practical = Practical(
        subject_id=subject_id,
        practical_number=next_practical_number(db, subject_id),
        title=title.strip(),
        description=description,
        learning_outcome=learning_outcome,
        difficulty=difficulty,
        max_marks=100,
        grade=grade,
        submission_date=submission_date,
        created_by=creator_id,
    )
    db.add(practical)
    audit(db, creator_id, "CREATE_PRACTICAL", "Practical", None, f"{subject_id}:{practical.title}")
    db.commit()
    db.refresh(practical)
    return practical


def update_practical(db: Session, practical_id: int, actor_id: int, **fields) -> Practical:
    practical = db.get(Practical, practical_id)
    if not practical:
        raise ValueError("Practical not found.")
    # Submission date is intentionally immutable after creation once assignments exist.
    for key in ("title", "description", "learning_outcome", "difficulty", "max_marks"):
        if key in fields:
            setattr(practical, key, fields[key])
    if "grade" in fields:
        grade = fields["grade"].strip().upper()
        if grade not in VALID_GRADES:
            raise ValueError("Grade must be one of A, B, C, D, E, or F.")
        practical.grade = grade
    if "subject_id" in fields and fields["subject_id"] != practical.subject_id:
        raise ValueError("A practical cannot be moved to another subject after creation.")
    audit(db, actor_id, "UPDATE_PRACTICAL", "Practical", practical.id, f"{practical.subject_id}:{practical.title}")
    db.commit()
    db.refresh(practical)
    return practical


def delete_practical(db: Session, practical_id: int, actor_id: int) -> None:
    practical = db.get(Practical, practical_id, options=[joinedload(Practical.assignments)])
    if not practical:
        raise ValueError("Practical not found.")
    for assignment in practical.assignments:
        if assignment.submission:
            raise ValueError("Cannot delete a practical that already has student submissions.")
    audit(db, actor_id, "DELETE_PRACTICAL", "Practical", practical.id, f"{practical.subject_id}:{practical.title}")
    db.delete(practical)
    db.commit()


# --------------------------------------------------------------------------
# Guarded master-data deletion (Administrator)
# --------------------------------------------------------------------------


def delete_department(db: Session, department_id: int, actor_id: int) -> None:
    department = db.get(Department, department_id)
    if not department:
        raise ValueError("Department not found.")
    subject_count = db.scalar(select(func.count(Subject.id)).where(Subject.department_id == department_id)) or 0
    if subject_count:
        raise ValueError(f"Cannot delete a department that still has {subject_count} subject(s). Move or delete them first.")
    audit(db, actor_id, "DELETE_DEPARTMENT", "Department", department.id, department.code)
    db.delete(department)
    db.commit()


def delete_subject(db: Session, subject_id: int, actor_id: int) -> None:
    subject = db.get(Subject, subject_id)
    if not subject:
        raise ValueError("Subject not found.")
    practical_count = db.scalar(select(func.count(Practical.id)).where(Practical.subject_id == subject_id)) or 0
    if practical_count:
        raise ValueError("Cannot delete a subject that still has practicals. Delete its practicals first.")
    faculty_count = db.scalar(select(func.count(FacultySubject.id)).where(FacultySubject.subject_id == subject_id)) or 0
    if faculty_count:
        raise ValueError("Cannot delete a subject that is assigned to faculty. Unassign it first.")
    audit(db, actor_id, "DELETE_SUBJECT", "Subject", subject.id, subject.code)
    db.delete(subject)
    db.commit()


def delete_user(db: Session, user_id: int, actor_id: int) -> None:
    if user_id == actor_id:
        raise ValueError("You cannot delete your own account.")
    user = db.get(User, user_id)
    if not user:
        raise ValueError("User not found.")
    practical_count = db.scalar(select(func.count(Practical.id)).where(Practical.created_by == user_id)) or 0
    if practical_count:
        raise ValueError("Cannot delete a faculty member who created practicals. Deactivate the account instead.")
    if user.student:
        raise ValueError("Cannot delete a user with a linked student profile. Deactivate the account instead.")
    evaluation_count = db.scalar(select(func.count(Evaluation.id)).where(Evaluation.evaluator_id == user_id)) or 0
    if evaluation_count:
        raise ValueError("Cannot delete a user who published evaluations. Deactivate the account instead.")
    audit(db, actor_id, "DELETE_USER", "User", user.id, user.username)
    db.delete(user)
    db.commit()


# --------------------------------------------------------------------------
# Faculty-scoped evaluation queue
# --------------------------------------------------------------------------


def submissions_for_faculty(db: Session, faculty_id: int, subject_id: int | None = None) -> list[Submission]:
    """Unpublished (or published) submissions belonging to practicals on subjects assigned to the faculty member."""
    statement = (
        select(Submission)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Practical, Practical.id == Assignment.practical_id)
        .join(FacultySubject, FacultySubject.subject_id == Practical.subject_id)
        .where(FacultySubject.faculty_id == faculty_id, Assignment.status.in_(["Submitted", "Late"]))
    )
    if subject_id:
        statement = statement.where(Practical.subject_id == subject_id)
    return list(db.scalars(statement.order_by(Submission.submitted_at)))


def faculty_practicals(db: Session, faculty_id: int, subject_id: int | None = None) -> list[Practical]:
    """Practicals on the subjects assigned to the faculty member."""
    statement = (
        select(Practical)
        .join(FacultySubject, FacultySubject.subject_id == Practical.subject_id)
        .where(FacultySubject.faculty_id == faculty_id)
        .order_by(FacultySubject.subject_id, Practical.practical_number)
    )
    if subject_id:
        statement = statement.where(Practical.subject_id == subject_id)
    return list(db.scalars(statement))
