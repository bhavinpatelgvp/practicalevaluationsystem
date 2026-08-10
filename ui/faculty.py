import pandas as pd
import streamlit as st
from datetime import date, timedelta
from sqlalchemy import select
from models.schema import Assignment, Practical, Student, Submission, Subject
from services.core_services import (
    assign_practical,
    build_practical_import_template,
    create_practical,
    delete_practical,
    faculty_practicals,
    grade_submission,
    import_practicals_from_dataframe,
    subjects_for_faculty,
    submissions_for_faculty,
    update_practical,
    validate_practical_import,
)
from core.rbac import has_permission

VALID_GRADES = ["A", "B", "C", "D", "E", "F"]


def _subject_labels(subjects: list[Subject]) -> dict[int, str]:
    return {subject.id: f"{subject.code} · {subject.name}" for subject in subjects}


def faculty_page(db, user) -> None:
    st.title("Faculty workspace")
    # require faculty access permission (administrators bypass)
    if not (user and (user.role and user.role.name == "Administrator" or has_permission(db, user, "faculty.access"))):
        st.error("You do not have permission to access the Faculty workspace.")
        return
    subjects = subjects_for_faculty(db, user.id)
    if not subjects:
        st.info("No subjects have been assigned to you yet. Contact the administrator to assign subjects.")
        return
    subject_labels = _subject_labels(subjects)
    st.caption(f"Teaching {len(subjects)} subject(s): {', '.join(subject_labels.values())}")

    practicals = faculty_practicals(db, user.id)
    submissions = submissions_for_faculty(db, user.id)
    pending_count = len([s for s in submissions if not s.evaluation])
    columns = st.columns(4)
    for column, label, value in zip(
        columns,
        ["Assigned subjects", "Practicals", "Submissions to evaluate", "Pending evaluation"],
        [len(subjects), len(practicals), len(submissions), pending_count],
    ):
        with column:
            st.metric(label, value)

    tab_create, tab_assign, tab_grade = st.tabs(["Create / manage practicals", "Assign to students", "Evaluate"])
    with tab_create:
        _practical_management(db, user.id, subject_labels)
    with tab_assign:
        _assignment_ui(db, user.id, subject_labels)
    with tab_grade:
        _evaluation_ui(db, user.id, subject_labels)


def _bulk_practical_import(db, user_id: int) -> None:
    st.subheader("Bulk import practicals")
    st.caption("Upload an Excel file to create multiple practicals across your assigned subjects.")
    with st.expander("Download sample template", expanded=False):
        st.download_button(
            "Download practical import template",
            build_practical_import_template(),
            file_name="practical_import_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.info("Required columns: Subject Code, Practical Title. Optional: Description, Learning Outcome, Difficulty, Grade, Submission Days, Submission Date.")
    uploaded = st.file_uploader("Choose Excel file", type=["xlsx", "xls"], key="practical_import_file")
    if uploaded is not None:
        try:
            rows = pd.read_excel(uploaded)
            preview = validate_practical_import(rows, db, user_id)
            valid_count = sum(1 for item in preview if item["ready"])
            bad_count = len(preview) - valid_count
            st.success(f"Validated {len(preview)} row(s): {valid_count} ready, {bad_count} with errors.")
            st.dataframe(pd.DataFrame(preview), hide_index=True, use_container_width=True)
            if valid_count and st.button("Import validated practicals"):
                summary = import_practicals_from_dataframe(rows, db, user_id, user_id)
                st.success(f"Imported {summary['imported']} practical(s); skipped {summary['skipped']}; failed {summary['failed']}")
                st.rerun()
        except Exception as error:
            st.error(f"Import failed: {error}")


def _practical_management(db, user_id: int, subject_labels: dict[int, str]) -> None:
    subjects = list(db.scalars(select(Subject).where(Subject.id.in_(subject_labels.keys())).order_by(Subject.code)))
    if not subjects:
        st.info("Create subjects first via the administrator.")
        return

    with st.expander("Bulk import practicals", expanded=False):
        _bulk_practical_import(db, user_id)

    with st.form("create_practical", clear_on_submit=True):
        st.caption("Create a new practical for one of your subjects")
        subject = st.selectbox("Subject", subjects, format_func=lambda item: f"{item.code} · {item.name}", key="create_practical_subject")
        title = st.text_input("Practical title")
        description = st.text_area("Description")
        learning_outcome = st.text_area("Learning outcome")
        difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=1)
        grade = st.selectbox("Grade", VALID_GRADES, index=0)
        submission_date = st.date_input("Submission date", value=date.today() + timedelta(days=7), min_value=date.today())
        if st.form_submit_button("Create practical"):
            if not title.strip():
                st.error("Enter a practical title.")
            else:
                create_practical(
                    db,
                    subject_id=subject.id,
                    title=title,
                    description=description,
                    learning_outcome=learning_outcome,
                    difficulty=difficulty,
                    grade=grade,
                    submission_date=submission_date,
                    creator_id=user_id,
                )
                st.success(f"Practical created for {subject.code}.")
                st.rerun()

    practicals = faculty_practicals(db, user_id)
    if not practicals:
        st.info("No practicals exist yet for your assigned subjects.")
        return
    selected = st.selectbox(
        "Practical to manage",
        practicals,
        format_func=lambda item: f"{item.subject.code} · P{item.practical_number} · {item.title}",
        key="manage_practical_select",
    )
    manage_tab, delete_tab = st.tabs(["Edit practical", "Delete practical"])
    with manage_tab:
        with st.form("update_practical_form"):
            edited_title = st.text_input("Title", value=selected.title)
            edited_description = st.text_area("Description", value=selected.description)
            edited_outcome = st.text_area("Learning outcome", value=selected.learning_outcome)
            difficulty_index = ["Easy", "Medium", "Hard"].index(selected.difficulty) if selected.difficulty in ["Easy", "Medium", "Hard"] else 1
            edited_difficulty = st.selectbox("Difficulty", ["Easy", "Medium", "Hard"], index=difficulty_index)
            grade_index = VALID_GRADES.index(selected.grade) if selected.grade in VALID_GRADES else 0
            edited_grade = st.selectbox("Grade", VALID_GRADES, index=grade_index)

            if selected.submission_date:
                st.caption(f"Submission date is fixed at {selected.submission_date:%d %b %Y} to keep assigned deadlines immutable.")
            else:
                st.caption("Submission date is not set; assignments fall back to the default submission window.")
            if st.form_submit_button("Save practical changes"):
                update_practical(
                    db,
                    selected.id,
                    user_id,
                    title=edited_title,
                    description=edited_description,
                    learning_outcome=edited_outcome,
                    difficulty=edited_difficulty,
                    grade=edited_grade,
                )
                st.success("Practical updated.")
                st.rerun()
    with delete_tab:
        st.warning("Deleting a practical also removes its assignments. Practicals with student submissions cannot be deleted.")
        if st.button("Delete this practical"):
            try:
                delete_practical(db, selected.id, user_id)
                st.success("Practical deleted.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))


def _assignment_ui(db, user_id: int, subject_labels: dict[int, str]) -> None:
    practicals = faculty_practicals(db, user_id)
    if not practicals:
        st.info("Create a practical first before assigning it to students.")
        return
    selected = st.selectbox(
        "Practical to assign",
        practicals,
        format_func=lambda item: f"{item.subject.code} · P{item.practical_number} · {item.title}",
        key="assign_practical_select",
    )
    assigned_ids = set(db.scalars(select(Assignment.student_id).where(Assignment.practical_id == selected.id)))
    students = list(db.scalars(select(Student).order_by(Student.enrollment_no)))
    if not students:
        st.info("No students are enrolled yet.")
        return
    unassigned = [student for student in students if student.id not in assigned_ids]
    if not unassigned:
        st.success("This practical is already assigned to every enrolled student.")
        return
    choices = {student.id: f"{student.enrollment_no} · {student.user.full_name}" for student in unassigned}
    scope = st.radio("Assign to", ["All eligible students", "Selected students"], horizontal=True)
    if scope == "All eligible students":
        st.caption(f"{len(unassigned)} student(s) will receive this practical.")
        if st.button("Assign to every enrolled student"):
            created = assign_practical(db, selected, user_id)
            st.success(f"Assigned to {created} students.")
            st.rerun()
    else:
        selected_students = st.multiselect(
            "Students to receive this practical",
            list(choices),
            format_func=lambda value: choices[value],
            key="assign_selected_students",
        )
        if st.button("Assign to selected students") and selected_students:
            created = assign_practical(db, selected, user_id, student_ids=selected_students)
            st.success(f"Assigned to {created} students.")
            st.rerun()


def _evaluation_ui(db, user_id: int, subject_labels: dict[int, str]) -> None:
    subjects = list(db.scalars(select(Subject).where(Subject.id.in_(subject_labels.keys())).order_by(Subject.code)))
    submissions = submissions_for_faculty(db, user_id)
    if not submissions:
        st.info("No submissions to evaluate for your subjects.")
        return
    subject_choices = {subject.id: f"{subject.code} · {subject.name}" for subject in subjects}
    subject_filter = st.selectbox(
        "Filter by subject",
        [None] + list(subject_choices),
        format_func=lambda value: "All subjects" if value is None else subject_choices[value],
        key="evaluate_subject_filter",
    )
    filtered = [item for item in submissions if subject_filter is None or item.assignment.practical.subject_id == subject_filter]
    if not filtered:
        st.info("No submissions for the selected subject.")
        return
    submission_choices = {
        item.id: f"{item.assignment.practical.subject.code} · P{item.assignment.practical.practical_number} · {item.assignment.student.enrollment_no}"
        for item in filtered
    }
    selected = st.selectbox("Submission to evaluate", list(submission_choices), format_func=lambda value: submission_choices[value], key="evaluate_submission_select")
    submission = db.get(Submission, selected)
    st.caption(f"Repository: {submission.github_url}")
    with st.form("evaluation_form"):
        grade = st.selectbox("Grade", VALID_GRADES)
        remarks = st.text_area("Remarks")
        suggestions = st.text_area("Suggestions")
        if st.form_submit_button("Publish evaluation", type="primary"):
            grade_submission(db, submission.id, user_id, grade, remarks, suggestions)
            st.success("Evaluation published.")
            st.rerun()
