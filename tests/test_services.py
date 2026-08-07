from datetime import date, datetime, timedelta
import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from database import Base
from auth import ensure_role, hash_password, verify_password
from models import Assignment, Department, FacultySubject, Practical, Student, Subject, Submission, User
from reports import excel_report, pdf_report
from services import (
    assign_faculty_subjects,
    assign_practical,
    build_practical_import_template,
    create_practical,
    delete_department,
    delete_practical,
    delete_subject,
    delete_user,
    faculty_practicals,
    grade_submission,
    import_practicals_from_dataframe,
    save_submission,
    subjects_for_faculty,
    submissions_for_faculty,
    update_practical,
    validate_bulk_user_import,
    validate_practical_import,
)


def setup_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def seed_world(db):
    faculty_role = ensure_role(db, "Faculty")
    student_role = ensure_role(db, "Student")
    admin_role = ensure_role(db, "Administrator")
    department = Department(name="CS", code="CS")
    db.add(department); db.flush()
    admin = User(username="admin", full_name="Admin", email="a@x", password_hash="x", role=admin_role)
    faculty = User(username="faculty", full_name="Faculty", email="f@x", password_hash="x", role=faculty_role)
    subject = Subject(code="CS1", name="Lab", semester=1, department=department)
    other_subject = Subject(code="CS2", name="Other Lab", semester=1, department=department)
    student_user = User(username="student", full_name="Student", email="s@x", password_hash="x", role=student_role)
    student = Student(user=student_user, enrollment_no="E1", semester=1)
    other_student_user = User(username="student2", full_name="Student 2", email="s2@x", password_hash="x", role=student_role)
    other_student = Student(user=other_student_user, enrollment_no="E2", semester=1)
    db.add_all([admin, faculty, subject, other_subject, student_user, student, other_student_user, other_student]); db.commit()
    return {
        "db": db,
        "department": department,
        "admin": admin,
        "faculty": faculty,
        "subject": subject,
        "other_subject": other_subject,
        "student": student,
        "other_student": other_student,
    }


def test_password_roundtrip():
    value = hash_password("secret")
    assert verify_password("secret", value)
    assert not verify_password("wrong", value)


def test_assign_submit_and_grade():
    db = setup_db()
    world = seed_world(db)
    practical = Practical(subject=world["subject"], practical_number=1, title="Build", created_by=world["faculty"].id, submission_days=7)
    db.add(practical); db.commit()
    assert assign_practical(db, practical, world["faculty"].id) == 2
    assignment = db.scalar(select(Assignment).where(Assignment.student_id == world["student"].id))
    submission = save_submission(db, assignment.id, "https://github.com/example/repo", world["student"].user_id)
    evaluation = grade_submission(db, submission.id, world["faculty"].id, "A", "Good", "Keep testing")
    assert evaluation.grade == "A"
    assert len(excel_report(db).getvalue()) > 0
    assert len(pdf_report(db).getvalue()) > 0


def test_invalid_repository_url_is_rejected():
    db = setup_db()
    with pytest.raises(ValueError, match="valid public GitHub"):
        save_submission(db, 999, "https://example.com/not-github", 1)


def test_invalid_grade_is_rejected():
    db = setup_db()
    with pytest.raises(ValueError, match="Grade must be one"):
        grade_submission(db, 999, 1, "A+", "Good", "Keep testing")


def test_assignment_uses_practical_submission_date():
    db = setup_db()
    world = seed_world(db)
    submission_date = date.today() + timedelta(days=10)
    practical = Practical(subject=world["subject"], practical_number=1, title="Build", created_by=world["faculty"].id, submission_date=submission_date)
    db.add(practical); db.commit()

    assign_practical(db, practical, world["faculty"].id)
    assignment = db.scalar(select(Assignment).where(Assignment.student_id == world["student"].id))
    assert assignment.deadline.date() == submission_date


def test_assign_faculty_subjects_and_scoping():
    db = setup_db()
    world = seed_world(db)
    assign_faculty_subjects(db, world["faculty"].id, [world["subject"].id], world["admin"].id)
    assert {subject.id for subject in subjects_for_faculty(db, world["faculty"].id)} == {world["subject"].id}
    assert subjects_for_faculty(db, world["other_student"].user_id) == []

    # replace the assignment set
    assign_faculty_subjects(db, world["faculty"].id, [world["other_subject"].id], world["admin"].id)
    assert {subject.id for subject in subjects_for_faculty(db, world["faculty"].id)} == {world["other_subject"].id}

    # idempotent
    assign_faculty_subjects(db, world["faculty"].id, [world["other_subject"].id], world["admin"].id)
    links = db.scalars(select(FacultySubject)).all()
    assert len(links) == 1


def test_faculty_only_sees_practicals_and_submissions_for_assigned_subjects():
    db = setup_db()
    world = seed_world(db)
    assign_faculty_subjects(db, world["faculty"].id, [world["subject"].id], world["admin"].id)
    my_practical = Practical(subject=world["subject"], practical_number=1, title="Mine", created_by=world["faculty"].id, submission_days=7)
    other_practical = Practical(subject=world["other_subject"], practical_number=1, title="Not mine", created_by=world["faculty"].id, submission_days=7)
    db.add_all([my_practical, other_practical]); db.commit()

    visible = faculty_practicals(db, world["faculty"].id)
    assert {p.title for p in visible} == {"Mine"}

    assign_practical(db, my_practical, world["faculty"].id)
    assignment = db.scalar(select(Assignment).where(Assignment.student_id == world["student"].id))
    save_submission(db, assignment.id, "https://github.com/example/repo", world["student"].user_id)
    queue = submissions_for_faculty(db, world["faculty"].id)
    assert {s.assignment.practical.title for s in queue} == {"Mine"}


def test_assign_practical_to_selected_students():
    db = setup_db()
    world = seed_world(db)
    practical = Practical(subject=world["subject"], practical_number=1, title="Build", created_by=world["faculty"].id, submission_days=7)
    db.add(practical); db.commit()
    created = assign_practical(db, practical, world["faculty"].id, student_ids=[world["student"].id])
    assert created == 1
    assignments = db.scalars(select(Assignment)).all()
    assert [a.student_id for a in assignments] == [world["student"].id]


def test_create_practical_stores_grade_and_increments_number():
    db = setup_db()
    world = seed_world(db)
    first = create_practical(db, world["subject"].id, "One", "d", "B", date.today(), world["faculty"].id)
    second = create_practical(db, world["subject"].id, "Two", "d", "A", date.today(), world["faculty"].id)
    assert (first.practical_number, second.practical_number) == (1, 2)
    assert first.grade == "B"
    assert second.grade == "A"


def test_invalid_grade_rejected_on_create():
    db = setup_db()
    world = seed_world(db)
    with pytest.raises(ValueError, match="Grade must be one"):
        create_practical(db, world["subject"].id, "One", "d", "A+", date.today(), world["faculty"].id)


def test_update_practical_changes_grade():
    db = setup_db()
    world = seed_world(db)
    practical = create_practical(db, world["subject"].id, "One", "d", "B", date.today(), world["faculty"].id)
    update_practical(db, practical.id, world["faculty"].id, grade="C", title="Updated")
    db.refresh(practical)
    assert practical.grade == "C"
    assert practical.title == "Updated"


def test_delete_practical_blocked_with_submissions():
    db = setup_db()
    world = seed_world(db)
    practical = create_practical(db, world["subject"].id, "Build", "d", "A", date.today(), world["faculty"].id)
    assign_practical(db, practical, world["faculty"].id)
    assignment = db.scalar(select(Assignment).where(Assignment.student_id == world["student"].id))
    save_submission(db, assignment.id, "https://github.com/example/repo", world["student"].user_id)
    with pytest.raises(ValueError, match="submissions"):
        delete_practical(db, practical.id, world["faculty"].id)


def test_delete_department_blocked_with_subjects():
    db = setup_db()
    world = seed_world(db)
    with pytest.raises(ValueError, match="subject"):
        delete_department(db, world["department"].id, world["admin"].id)


def test_delete_subject_blocked_with_practicals():
    db = setup_db()
    world = seed_world(db)
    create_practical(db, world["subject"].id, "Build", "d", "A", date.today(), world["faculty"].id)
    with pytest.raises(ValueError, match="practicals"):
        delete_subject(db, world["subject"].id, world["admin"].id)


def test_delete_subject_blocked_when_assigned_to_faculty():
    db = setup_db()
    world = seed_world(db)
    assign_faculty_subjects(db, world["faculty"].id, [world["subject"].id], world["admin"].id)
    with pytest.raises(ValueError, match="assigned to faculty"):
        delete_subject(db, world["subject"].id, world["admin"].id)


def test_delete_user_blocked_for_student_profile_and_self():
    db = setup_db()
    world = seed_world(db)
    with pytest.raises(ValueError, match="student profile"):
        delete_user(db, world["student"].user_id, world["admin"].id)
    with pytest.raises(ValueError, match="own account"):
        delete_user(db, world["admin"].id, world["admin"].id)


def test_validate_bulk_user_import_marks_missing_and_duplicate_rows():
    db = setup_db()
    seed_world(db)
    rows = pd.DataFrame(
        [
            {"Enrollment No": "E100", "Name": "Alice", "Email": "alice@example.com", "Mobile": "9876543210", "Course": "MCA", "Semester": "3", "Division": "A", "Batch": "B1"},
            {"Enrollment No": "", "Name": "Bob", "Email": "bob@example.com", "Mobile": "9876543210", "Course": "MCA", "Semester": "3", "Division": "A", "Batch": "B1"},
            {"Enrollment No": "E100", "Name": "Alice 2", "Email": "alice2@example.com", "Mobile": "9876543210", "Course": "MCA", "Semester": "3", "Division": "A", "Batch": "B1"},
        ]
    )

    preview = validate_bulk_user_import(rows, "student", db)

    assert preview[0]["ready"] is True
    assert preview[1]["ready"] is False
    assert "required" in preview[1]["reason"].lower()
    assert preview[2]["duplicate"] is True


def test_build_practical_import_template_returns_bytes():
    template = build_practical_import_template()
    assert len(template) > 0


def test_validate_practical_import_scopes_to_assigned_subjects():
    db = setup_db()
    world = seed_world(db)
    assign_faculty_subjects(db, world["faculty"].id, [world["subject"].id], world["admin"].id)
    rows = pd.DataFrame(
        [
            {"Subject Code": "CS1", "Practical Title": "Lab 1", "Description": "d", "Learning Outcome": "o", "Difficulty": "Medium", "Grade": "B", "Submission Days": 7, "Submission Date": ""},
            {"Subject Code": "CS2", "Practical Title": "Other", "Description": "d", "Learning Outcome": "o", "Difficulty": "Medium", "Grade": "A", "Submission Days": 5, "Submission Date": ""},
            {"Subject Code": "CS1", "Practical Title": "", "Description": "d", "Learning Outcome": "o", "Difficulty": "Medium", "Grade": "B", "Submission Days": 7, "Submission Date": ""},
        ]
    )
    preview = validate_practical_import(rows, db, world["faculty"].id)
    assert preview[0]["ready"] is True
    assert preview[1]["ready"] is False
    assert "not assigned" in preview[1]["error_message"]
    assert preview[2]["ready"] is False


def test_import_practicals_from_dataframe():
    db = setup_db()
    world = seed_world(db)
    assign_faculty_subjects(db, world["faculty"].id, [world["subject"].id], world["admin"].id)
    rows = pd.DataFrame(
        [
            {"Subject Code": "CS1", "Practical Title": "Lab 1", "Description": "d", "Learning Outcome": "o", "Difficulty": "Medium", "Grade": "B", "Submission Days": 7, "Submission Date": ""},
            {"Subject Code": "CS1", "Practical Title": "Lab 2", "Description": "d", "Learning Outcome": "o", "Difficulty": "Hard", "Grade": "A", "Submission Days": 10, "Submission Date": ""},
            {"Subject Code": "CS2", "Practical Title": "Other", "Description": "d", "Learning Outcome": "o", "Difficulty": "Easy", "Grade": "C", "Submission Days": 5, "Submission Date": ""},
        ]
    )
    summary = import_practicals_from_dataframe(rows, db, world["faculty"].id, world["faculty"].id)
    assert summary["imported"] == 2  # CS2 is not assigned so gets skipped
    assert summary["skipped"] == 1
    practicals = db.scalars(select(Practical)).all()
    titles = {p.title for p in practicals}
    assert titles == {"Lab 1", "Lab 2"}
    numbers = {p.practical_number for p in practicals}
    assert numbers == {1, 2}
