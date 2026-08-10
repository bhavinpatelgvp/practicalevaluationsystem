import pandas as pd
import streamlit as st
from datetime import date, timedelta
from sqlalchemy import select
from models.schema import Assignment, FacultySubject, Practical, Program, Student, Submission, Subject
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
        st.info("Required columns: **Subject Code**, **Practical Title**. Optional: Description, Learning Outcome, Difficulty (Easy/Medium/Hard), Submission Date (YYYY-MM-DD). Grade and Submission Days are no longer needed.")
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
        submission_date = st.date_input("Submission date (optional)", value=None, min_value=date.today())
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
                    grade="A",  # default; set per-student during evaluation
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

            if selected.submission_date:
                st.caption(f"Submission date is fixed at {selected.submission_date:%d %b %Y} to keep assigned deadlines immutable.")
            else:
                st.caption("Submission date is not set; no deadline will be enforced.")
            if st.form_submit_button("Save practical changes"):
                update_practical(
                    db,
                    selected.id,
                    user_id,
                    title=edited_title,
                    description=edited_description,
                    learning_outcome=edited_outcome,
                    difficulty=edited_difficulty,
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
    st.subheader("Assign practical to students")
    st.caption("Filter students by Programme, Semester, and Subject to assign practicals.")

    # 1. Fetch faculty's assigned subjects
    fac_subjects = subjects_for_faculty(db, user_id)
    if not fac_subjects:
        st.info("No subjects have been assigned to you yet.")
        return

    # Find distinct programmes linked to these subjects (or all programmes if subjects lack program_id)
    linked_prog_ids = {s.program_id for s in fac_subjects if s.program_id is not None}
    if linked_prog_ids:
        programs = list(db.scalars(select(Program).where(Program.id.in_(linked_prog_ids)).order_by(Program.code)))
    else:
        programs = list(db.scalars(select(Program).order_by(Program.code)))

    if not programs:
        st.info("No programmes have been configured yet.")
        return

    prog_choices = {p.id: f"{p.code} · {p.name}" for p in programs}

    col1, col2 = st.columns(2)
    with col1:
        selected_prog_id = st.selectbox("1. Select Programme", list(prog_choices), format_func=prog_choices.get, key="assign_prog_select")
        chosen_program = db.get(Program, selected_prog_id)
    
    with col2:
        max_sem = chosen_program.total_semesters if chosen_program else 8
        semesters_available = list(range(1, max_sem + 1))
        selected_semester = st.selectbox("2. Select Semester", semesters_available, index=0, format_func=lambda s: f"Semester {s}", key="assign_sem_select")

    # Filter faculty subjects for the selected program and semester
    matching_subjects = [
        s for s in fac_subjects
        if (s.program_id == selected_prog_id or s.program_id is None) and (s.semester == selected_semester or s.semester is None)
    ]
    # Fallback to all faculty subjects if none strictly matched
    if not matching_subjects:
        matching_subjects = [s for s in fac_subjects if s.program_id == selected_prog_id or s.program_id is None]
    if not matching_subjects:
        matching_subjects = fac_subjects

    subj_choices = {s.id: f"{s.code} · {s.name} (Sem {s.semester})" for s in matching_subjects}
    
    col3, col4 = st.columns(2)
    with col3:
        selected_subj_id = st.selectbox("3. Select Subject", list(subj_choices), format_func=subj_choices.get, key="assign_subj_select")
        chosen_subject = db.get(Subject, selected_subj_id)

    # 4. Fetch practicals for selected subject
    practicals = list(db.scalars(select(Practical).where(Practical.subject_id == selected_subj_id).order_by(Practical.practical_number)))
    if not practicals:
        with col4:
            st.warning("No practicals created for this subject.")
        st.info(f"Create a practical for {chosen_subject.code} in the 'Create / manage practicals' tab first.")
        return

    pract_choices = {p.id: f"P{p.practical_number} · {p.title} (Due: {p.submission_date.strftime('%d %b %Y') if p.submission_date else 'No date'})" for p in practicals}
    with col4:
        selected_pract_id = st.selectbox("4. Select Practical", list(pract_choices), format_func=pract_choices.get, key="assign_pract_select")
        selected_practical = db.get(Practical, selected_pract_id)

    st.markdown("---")

    # Fetch students enrolled in this program and semester
    student_query = select(Student).where(
        (Student.program_id == selected_prog_id) | ((Student.program_id.is_(None)) & (Student.program == chosen_program.code)),
        Student.semester == selected_semester,
    ).order_by(Student.enrollment_no)
    students = list(db.scalars(student_query))

    if not students:
        st.info(f"No students found enrolled in {chosen_program.code} - Semester {selected_semester}.")
        return

    # Check unassigned vs assigned
    assigned_ids = set(db.scalars(select(Assignment.student_id).where(Assignment.practical_id == selected_practical.id)))
    unassigned = [s for s in students if s.id not in assigned_ids]
    already_assigned = [s for s in students if s.id in assigned_ids]

    # Metrics summary
    mcol1, mcol2, mcol3 = st.columns(3)
    with mcol1:
        st.metric(f"Total in {chosen_program.code} Sem {selected_semester}", len(students))
    with mcol2:
        st.metric("Eligible to Assign", len(unassigned))
    with mcol3:
        st.metric("Already Assigned", len(already_assigned))

    if not unassigned:
        st.success(f"This practical is already assigned to all {len(students)} enrolled student(s) in {chosen_program.code} Semester {selected_semester}.")
    else:
        choices = {s.id: f"{s.enrollment_no} · {s.user.full_name}" for s in unassigned}
        scope = st.radio(
            "Assignment Mode",
            [f"Assign to all eligible students ({len(unassigned)})", "Select specific students from list"],
            horizontal=True,
            key="assign_mode_radio",
        )
        if scope.startswith("Assign to all"):
            st.caption(f"Clicking the button below will immediately assign Practical P{selected_practical.practical_number} to all {len(unassigned)} students.")
            if st.button("Assign to all in one click", type="primary"):
                created = assign_practical(db, selected_practical, user_id, student_ids=[s.id for s in unassigned])
                st.success(f"Assigned practical to {created} student(s).")
                st.rerun()
        else:
            selected_students = st.multiselect(
                "Select students to receive this practical",
                list(choices),
                format_func=choices.get,
                key="assign_selected_students",
            )
            if st.button("Assign to selected students", type="primary"):
                if not selected_students:
                    st.error("Select at least one student from the list.")
                else:
                    created = assign_practical(db, selected_practical, user_id, student_ids=selected_students)
                    st.success(f"Assigned practical to {created} student(s).")
                    st.rerun()

    if already_assigned:
        with st.expander(f"View already assigned students ({len(already_assigned)})", expanded=False):
            assigned_rows = []
            for s in already_assigned:
                assign_rec = db.scalar(select(Assignment).where(Assignment.practical_id == selected_practical.id, Assignment.student_id == s.id))
                status_str = assign_rec.status if assign_rec else "Assigned"
                assigned_rows.append({"Enrollment": s.enrollment_no, "Name": s.user.full_name, "Status": status_str})
            st.dataframe(pd.DataFrame(assigned_rows), hide_index=True, use_container_width=True)


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
