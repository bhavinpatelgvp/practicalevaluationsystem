import streamlit as st
from sqlalchemy import select
from models.schema import Assignment, Student
from services.core_services import save_submission


def student_page(db, student: Student) -> None:
    st.title("My practicals")
    assignments = db.scalars(select(Assignment).where(Assignment.student_id == student.id).order_by(Assignment.deadline)).all()
    for assignment in assignments:
        with st.expander(f"P{assignment.practical.practical_number} · {assignment.practical.title} · {assignment.status}"):
            st.write(f"Deadline: {assignment.deadline:%d %b %Y, %I:%M %p}")
            if assignment.submission:
                st.link_button("Open GitHub repository", assignment.submission.github_url)
                if assignment.submission.evaluation:
                    ev = assignment.submission.evaluation
                    st.success(f"Published grade: {ev.grade}")
                    st.write(ev.remarks)
            else:
                with st.form(f"submit-{assignment.id}"):
                    url = st.text_input("GitHub repository URL")
                    commit = st.text_input("Commit hash")
                    branch = st.text_input("Branch", "main")
                    notes = st.text_area("Documentation / remarks")
                    if st.form_submit_button("Submit repository"):
                        try:
                            save_submission(db, assignment.id, url, student.user_id, commit_hash=commit, branch=branch, documentation=notes)
                            st.success("Submission recorded"); st.rerun()
                        except ValueError as error:
                            st.error(str(error))
