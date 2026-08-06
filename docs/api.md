# API Documentation

The current release is a Streamlit application and does not expose a public REST API. The stable service boundary is:

- `assign_faculty_subjects(db, faculty_id, subject_ids, actor_id)` replaces a faculty member's subject assignments (subject-wise Faculty); the faculty workspace only shows assigned subjects.
- `subjects_for_faculty(db, faculty_id)` and `faculty_subject_ids(db, faculty_id)` expose the assigned-subject scope.
- `faculty_practicals(db, faculty_id, subject_id=None)` lists practicals for the faculty member's assigned subjects only.
- `create_practical(db, subject_id, title, description, max_marks, submission_date, creator_id, ...)`, `update_practical(...)`, and `delete_practical(...)` manage practicals; deletion is blocked once submissions exist.
- `assign_practical(db, practical, actor_id, student_ids=None)` creates missing assignments for every enrolled student or a chosen subset.
- `save_submission(db, assignment_id, github_url, actor_id, ...)` validates and stores a repository submission.
- `grade_submission(db, submission_id, evaluator_id, grade, remarks, suggestions)` validates an `A`-`F` grade, publishes the evaluation, and writes an audit event.
- `submissions_for_faculty(db, faculty_id, subject_id=None)` returns the evaluation queue scoped to assigned subjects.
- `delete_department(db, department_id, actor_id)`, `delete_subject(db, subject_id, actor_id)`, and `delete_user(db, user_id, actor_id)` are referentially guarded: deletion is rejected while dependent records exist or the row is in use.
- `marks_dataframe(db)`, `excel_report(db)`, and `pdf_report(db)` generate report artifacts.

If a REST layer is added, preserve these service functions as the application layer and add explicit request schemas, authentication middleware, rate limiting, OpenAPI documentation, and idempotency keys for bulk operations.
