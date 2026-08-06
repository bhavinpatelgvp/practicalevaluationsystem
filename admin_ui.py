import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from auth import hash_password
from models import Department, Role, Subject, User
from reports import excel_report, marks_dataframe, pdf_report
from services import (
    assign_faculty_subjects,
    audit,
    build_bulk_import_template,
    build_subject_import_template,
    delete_department,
    delete_subject,
    delete_user,
    import_bulk_users_from_dataframe,
    import_subjects_from_dataframe,
    validate_bulk_user_import,
    validate_subject_import,
)


def _roles(db) -> dict[int, str]:
    return {role.id: role.name for role in db.scalars(select(Role).order_by(Role.name))}


def _role_id(db, name: str) -> int | None:
    return db.scalar(select(Role.id).where(Role.name == name))


def _department_labels(db) -> dict[int, str]:
    return {item.id: f"{item.code} · {item.name}" for item in db.scalars(select(Department).order_by(Department.code))}


def _subject_labels(db) -> dict[int, str]:
    return {item.id: f"{item.code} · {item.name}" for item in db.scalars(select(Subject).order_by(Subject.code))}


def _faculty_users(db) -> list[User]:
    return list(
        db.scalars(
            select(User).where(User.role_id == _role_id(db, "Faculty")).order_by(User.full_name)
        )
    )


def _commit_with_audit(db, user_id: int, action: str, entity: str, entity_id: int | None = None, details: str = "") -> None:
    audit(db, user_id, action, entity, entity_id, details)
    db.commit()


def _trigger_refresh() -> None:
    if "refresh_counter" not in st.session_state:
        st.session_state.refresh_counter = 0
    st.session_state.refresh_counter += 1
    try:
        st.rerun()
    except Exception:
        st.experimental_rerun()


def _department_crud(db, user_id: int) -> None:
    st.subheader("Department master data")
    departments = list(db.scalars(select(Department).order_by(Department.code)))
    if departments:
        st.dataframe(
            pd.DataFrame([{"Code": item.code, "Name": item.name, "Subjects": len(item.subjects)} for item in departments]),
            hide_index=True, use_container_width=True,
        )
    with st.form("add_department", clear_on_submit=True):
        st.caption("Add department")
        code = st.text_input("Department code")
        name = st.text_input("Department name")
        if st.form_submit_button("Add department"):
            if not code.strip() or not name.strip():
                st.error("Enter both a department code and name.")
            else:
                db.add(Department(code=code.strip().upper(), name=name.strip()))
                try:
                    _commit_with_audit(db, user_id, "CREATE_DEPARTMENT", "Department")
                    st.success("Department added.")
                    _trigger_refresh()
                except IntegrityError:
                    db.rollback(); st.error("That department code or name already exists.")
    if departments:
        update_column, delete_column = st.columns(2)
        with update_column:
            labels = {item.id: f"{item.code} · {item.name}" for item in departments}
            selected = st.selectbox("Update department", list(labels), format_func=labels.get, key="update_department_select")
            with st.form("update_department", clear_on_submit=True):
                edited_code = st.text_input("Code", value=db.get(Department, selected).code)
                edited_name = st.text_input("Name", value=db.get(Department, selected).name)
                if st.form_submit_button("Save changes"):
                    department = db.get(Department, selected)
                    department.code = edited_code.strip().upper() or department.code
                    department.name = edited_name.strip() or department.name
                    try:
                        _commit_with_audit(db, user_id, "UPDATE_DEPARTMENT", "Department", department.id)
                        st.success("Department updated.")
                        _trigger_refresh()
                    except IntegrityError:
                        db.rollback(); st.error("That department code or name already exists.")
        with delete_column:
            st.caption("Delete department")
            st.caption("A department with subjects cannot be deleted.")
            if st.button("Delete selected department", type="secondary"):
                try:
                    delete_department(db, selected, user_id)
                    st.success("Department deleted.")
                    _trigger_refresh()
                except ValueError as error:
                    st.error(str(error))


def _subject_crud(db, user_id: int) -> None:
    st.subheader("Subject master data")
    subjects = list(db.scalars(select(Subject).order_by(Subject.code)))
    departments = _department_labels(db)
    with st.expander("Bulk Subject Import", expanded=False):
        st.caption("Upload semester-wise subject data from Excel with validation and preview.")
        uploaded = st.file_uploader("Choose Excel file", type=["xlsx", "xls"], key="subject_import_file")
        if uploaded is not None:
            try:
                rows = pd.read_excel(uploaded)
                preview = validate_subject_import(rows, db)
                st.success(f"Validated {len(preview)} row(s).")
                st.dataframe(pd.DataFrame(preview), hide_index=True, use_container_width=True)
                if st.button("Import validated subjects"):
                    summary = import_subjects_from_dataframe(rows, db, user_id)
                    st.success(f"Imported {summary['imported']} subject(s); updated {summary['updated']}; skipped {summary['skipped']}; failed {summary['failed']}")
                    _trigger_refresh()
            except Exception as error:
                st.error(f"Import failed: {error}")
        cols = st.columns(2)
        with cols[0]:
            st.download_button("Download sample template", build_subject_import_template(), file_name="subject_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with cols[1]:
            st.info("The template uses the expected columns for code, name, semester, course, department, credits, subject type, and status.")
    if subjects:
        st.dataframe(
            pd.DataFrame(
                [{"Code": item.code, "Name": item.name, "Semester": item.semester, "Department": item.department.code} for item in subjects]
            ),
            hide_index=True, use_container_width=True,
        )
    if not departments:
        st.info("Create a department before adding subjects.")
        return
    with st.form("add_subject", clear_on_submit=True):
        st.caption("Add subject")
        code = st.text_input("Subject code")
        name = st.text_input("Subject name")
        semester = st.number_input("Semester", min_value=1, max_value=12, value=1)
        department_id = st.selectbox("Department", list(departments), format_func=departments.get, key="add_subject_department")
        if st.form_submit_button("Add subject"):
            if not code.strip() or not name.strip():
                st.error("Enter a subject code and name.")
            else:
                db.add(Subject(code=code.strip().upper(), name=name.strip(), semester=int(semester), department_id=department_id))
                try:
                    _commit_with_audit(db, user_id, "CREATE_SUBJECT", "Subject")
                    st.success("Subject added.")
                    _trigger_refresh()
                except IntegrityError:
                    db.rollback(); st.error("That subject code already exists.")
    if subjects:
        update_column, delete_column = st.columns(2)
        with update_column:
            labels = {item.id: f"{item.code} · {item.name}" for item in subjects}
            selected = st.selectbox("Update subject", list(labels), format_func=labels.get, key="update_subject_select")
            subject = db.get(Subject, selected)
            with st.form("update_subject", clear_on_submit=True):
                edited_code = st.text_input("Code", value=subject.code)
                edited_name = st.text_input("Name", value=subject.name)
                edited_semester = st.number_input("Semester", min_value=1, max_value=12, value=subject.semester)
                default_index = list(departments).index(subject.department_id) if subject.department_id in departments else 0
                edited_department = st.selectbox("Department", list(departments), format_func=departments.get, index=default_index, key="update_subject_department")
                if st.form_submit_button("Save changes"):
                    subject.code = edited_code.strip().upper() or subject.code
                    subject.name = edited_name.strip() or subject.name
                    subject.semester = int(edited_semester)
                    subject.department_id = edited_department
                    try:
                        _commit_with_audit(db, user_id, "UPDATE_SUBJECT", "Subject", subject.id)
                        st.success("Subject updated.")
                        _trigger_refresh()
                    except IntegrityError:
                        db.rollback(); st.error("That subject code already exists.")
        with delete_column:
            st.caption("Delete subject")
            st.caption("A subject assigned to faculty or with practicals cannot be deleted.")
            if st.button("Delete selected subject", type="secondary"):
                try:
                    delete_subject(db, selected, user_id)
                    st.success("Subject deleted.")
                    _trigger_refresh()
                except ValueError as error:
                    st.error(str(error))


def _faculty_crud(db, user_id: int) -> None:
    st.subheader("Faculty accounts and subject-wise assignment")
    faculty = _faculty_users(db)
    all_subjects = _subject_labels(db)
    if faculty:
        rows = []
        for member in faculty:
            assigned = sorted(link.subject.code for link in member.faculty_subjects)
            rows.append({"Name": member.full_name, "Username": member.username, "Email": member.email, "Assigned subjects": ", ".join(assigned) or "—", "Active": "Yes" if member.is_active else "No"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    else:
        st.info("No faculty accounts yet. Create one below.")

    if not all_subjects:
        st.info("Create subjects first, then assign them to faculty.")
    else:
        st.caption("Add faculty profile")
        non_faculty = db.scalars(
            select(User).where(User.role_id != _role_id(db, "Faculty")).order_by(User.full_name)
        ).all()
        non_faculty_labels = {item.id: f"{item.full_name} ({item.username})" for item in non_faculty}
        with st.form("add_faculty", clear_on_submit=True):
            mode = st.radio("How do you want to create the faculty account?", ["New account", "Promote an existing user"], horizontal=True)
            username = st.text_input("Username") if mode == "New account" else None
            full_name = st.text_input("Full name") if mode == "New account" else None
            email = st.text_input("Email") if mode == "New account" else None
            password = st.text_input("Temporary password", type="password") if mode == "New account" else None
            existing_user_id = st.selectbox("Choose user", list(non_faculty_labels), format_func=non_faculty_labels.get, key="faculty_existing_user") if mode == "Promote an existing user" else None
            assigned_subjects = st.multiselect("Subjects assigned to this faculty member", list(all_subjects), format_func=lambda value: all_subjects[value], key="add_faculty_subjects")
            if st.form_submit_button("Create faculty profile"):
                if mode == "New account":
                    if not all([username, full_name, email, password]):
                        st.error("Complete username, full name, email, and password.")
                    else:
                        try:
                            target = User(username=username.strip(), full_name=full_name.strip(), email=email.strip(), password_hash=hash_password(password), role_id=_role_id(db, "Faculty"))
                            db.add(target); db.flush()
                        except IntegrityError:
                            db.rollback(); st.error("That username or email already exists.")
                        else:
                            assign_faculty_subjects(db, target.id, assigned_subjects, user_id)
                            _commit_with_audit(db, user_id, "CREATE_FACULTY", "User", target.id)
                            st.success("Faculty account created.")
                            _trigger_refresh()
                else:
                    if not existing_user_id:
                        st.error("Select a user to promote.")
                    else:
                        target = db.get(User, existing_user_id)
                        target.role_id = _role_id(db, "Faculty")
                        assign_faculty_subjects(db, target.id, assigned_subjects, user_id)
                        _commit_with_audit(db, user_id, "PROMOTE_FACULTY", "User", target.id)
                        st.success("User promoted to faculty.")
                        _trigger_refresh()

    if faculty:
        st.caption("Edit faculty profile and subject assignments")
        faculty_labels = {item.id: f"{item.full_name} ({item.username})" for item in faculty}
        selected = st.selectbox("Faculty member", list(faculty_labels), format_func=faculty_labels.get, key="edit_faculty_select")
        member = db.get(User, selected)
        current_ids = [link.subject_id for link in member.faculty_subjects if link.subject_id in all_subjects]
        with st.form("update_faculty", clear_on_submit=True):
            edited_name = st.text_input("Full name", value=member.full_name)
            edited_email = st.text_input("Email", value=member.email)
            edited_active = st.checkbox("Active account", value=member.is_active)
            edited_subjects = st.multiselect(
                "Assigned subjects",
                list(all_subjects),
                default=current_ids,
                format_func=lambda value: all_subjects[value],
                key="edit_faculty_subjects",
            )
            new_password = st.text_input("Reset password (leave blank to keep)", type="password")
            if st.form_submit_button("Save changes"):
                member.full_name = edited_name.strip() or member.full_name
                member.email = edited_email.strip() or member.email
                member.is_active = edited_active
                if new_password:
                    member.password_hash = hash_password(new_password)
                try:
                    assign_faculty_subjects(db, member.id, edited_subjects, user_id)
                    _commit_with_audit(db, user_id, "UPDATE_FACULTY", "User", member.id)
                    st.success("Faculty profile updated.")
                    _trigger_refresh()
                except IntegrityError:
                    db.rollback(); st.error("That email is already in use by another account.")
        if st.button(f"Delete {member.full_name}", type="secondary"):
            try:
                delete_user(db, member.id, user_id)
                st.success("Faculty account deleted.")
                _trigger_refresh()
            except ValueError as error:
                st.error(str(error))


def _user_crud(db, user_id: int) -> None:
    st.subheader("User accounts")
    users = list(db.scalars(select(User).order_by(User.username)))
    roles = _roles(db)
    if users:
        st.dataframe(
            pd.DataFrame(
                [{"Username": item.username, "Name": item.full_name, "Email": item.email, "Role": roles[item.role_id], "Active": "Yes" if item.is_active else "No"} for item in users]
            ),
            hide_index=True, use_container_width=True,
        )
    with st.form("create_user", clear_on_submit=True):
        st.caption("Create user account")
        username = st.text_input("Username")
        full_name = st.text_input("Full name")
        email = st.text_input("Email")
        password = st.text_input("Temporary password", type="password")
        role_id = st.selectbox("Role", list(roles), format_func=roles.get, key="create_user_role")
        if st.form_submit_button("Create user"):
            if not all([username.strip(), full_name.strip(), email.strip(), password]):
                st.error("Complete all fields.")
            else:
                db.add(User(username=username.strip(), full_name=full_name.strip(), email=email.strip(), password_hash=hash_password(password), role_id=role_id))
                try:
                    _commit_with_audit(db, user_id, "CREATE_USER", "User")
                    st.success("User account created.")
                    _trigger_refresh()
                except IntegrityError:
                    db.rollback(); st.error("That username or email already exists.")
    if users:
        update_column, delete_column = st.columns(2)
        with update_column:
            user_labels = {item.id: f"{item.username} · {roles[item.role_id]}" for item in users}
            selected = st.selectbox("Update user", list(user_labels), format_func=user_labels.get, key="update_user_select")
            target = db.get(User, selected)
            with st.form("update_user", clear_on_submit=True):
                edited_name = st.text_input("Full name", value=target.full_name)
                edited_email = st.text_input("Email", value=target.email)
                edited_active = st.checkbox("Active account", value=target.is_active)
                default_role_index = list(roles).index(target.role_id) if target.role_id in roles else 0
                edited_role = st.selectbox("Role", list(roles), index=default_role_index, format_func=roles.get, key="update_user_role")
                new_password = st.text_input("Reset password (leave blank to keep)", type="password")
                if st.form_submit_button("Save changes"):
                    target.full_name = edited_name.strip() or target.full_name
                    target.email = edited_email.strip() or target.email
                    target.is_active = edited_active
                    target.role_id = edited_role
                    if new_password:
                        target.password_hash = hash_password(new_password)
                    try:
                        _commit_with_audit(db, user_id, "UPDATE_USER", "User", target.id)
                        st.success("User updated.")
                        _trigger_refresh()
                    except IntegrityError:
                        db.rollback(); st.error("That email is already in use by another account.")
        with delete_column:
            st.caption("Delete user")
            st.caption("Users with practicals, evaluations, or a student profile must be deactivated instead.")
            if st.button("Delete selected user", type="secondary"):
                try:
                    delete_user(db, selected, user_id)
                    st.success("User deleted.")
                    _trigger_refresh()
                except ValueError as error:
                    st.error(str(error))


def _reports_ui(db) -> None:
    report_data = marks_dataframe(db)
    st.subheader("Evaluation report")
    st.dataframe(report_data, hide_index=True, use_container_width=True)
    csv_data = report_data.to_csv(index=False).encode("utf-8")
    downloads = st.container()
    with downloads:
        cols = st.columns(3)
        with cols[0]:
            st.download_button("Download CSV", csv_data, "evaluation-report.csv", "text/csv")
        with cols[1]:
            st.download_button("Download XLSX", excel_report(db), "evaluation-report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with cols[2]:
            st.download_button("Download PDF", pdf_report(db), "evaluation-report.pdf", "application/pdf")


def _bulk_import_ui(db, user_id: int) -> None:
    st.subheader("Bulk user import")
    st.caption("Upload an Excel file to validate and import students, faculty, or administrators.")
    import_type = st.selectbox("Import type", ["student", "faculty", "admin"], format_func=lambda value: value.title())
    uploaded = st.file_uploader("Choose Excel file", type=["xlsx", "xls"], key="bulk_import_file")
    if uploaded is not None:
        try:
            data = pd.read_excel(uploaded)
            preview = validate_bulk_user_import(data, import_type, db)
            st.success(f"Validated {len(preview)} row(s).")
            st.dataframe(pd.DataFrame(preview), hide_index=True, use_container_width=True)
            if st.button("Import validated rows"):
                summary = import_bulk_users_from_dataframe(data, import_type, db, user_id)
                st.success(f"Imported {summary['imported']} user(s); skipped {summary['skipped']}; failed {summary['failed']}")
                _trigger_refresh()
        except Exception as error:
            st.error(f"Import failed: {error}")
    cols = st.columns(2)
    with cols[0]:
        template_bytes = build_bulk_import_template(import_type)
        st.download_button("Download sample template", template_bytes, file_name=f"{import_type}_template.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with cols[1]:
        st.info("Templates include the expected columns for each import type.")


def administrator_page(db, user: User) -> None:
    st.title("Administrator workspace")
    st.caption("Manage master data, faculty, user accounts, and evaluation reports.")
    master_tab, faculty_tab, users_tab, import_tab, reports_tab = st.tabs(["Master data", "Faculty", "Users", "Import", "Reports"])
    with master_tab:
        department_tab, subject_tab = st.tabs(["Departments", "Subjects"])
        with department_tab:
            _department_crud(db, user.id)
        with subject_tab:
            _subject_crud(db, user.id)
    with faculty_tab:
        _faculty_crud(db, user.id)
    with users_tab:
        _user_crud(db, user.id)
    with import_tab:
        _bulk_import_ui(db, user.id)
    with reports_tab:
        _reports_ui(db)
