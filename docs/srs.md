# System Requirements Specification

## Scope
TPEMS manages practical assignment, student repository submission, faculty evaluation, result publication, auditability, and academic reporting for multiple programs, departments, and semesters.

## Actors
- Administrator manages master data, users, and reports.
- Faculty creates practicals, assigns them, monitors submissions, evaluates, and publishes marks.
- Students view assignments, submit or update repositories before the deadline, and view published results.

## Functional requirements

1. The system allows an administrator to create, update, and delete master data of Department, Faculty, Subject, subject wise Faculty and users.
2. Every protected action is role checked and auditable.
3. A practical assignment has immutable assignment time and a calculated deadline.
4. One student has at most one submission per practical assignment.
5. A submission records URL, commit, branch, notes, time, and late status.
6. Evaluation stores criterion marks, total, grade, remarks, suggestions, evaluator, and publication state.
7. Reports can be exported in CSV-compatible data, XLSX, and PDF formats.
8. Dashboards expose completion, pending, late, and average-mark indicators.

## Non-functional requirements

- MySQL 8, normalized relational schema, indexed search columns, and SQLAlchemy parameterization.
- Passwords use bcrypt; secrets are environment-driven.
- Target scale: 10,000+ students with pagination and database-side aggregation in the next iteration.
- Accessibility: clear labels, status text, keyboard-friendly Streamlit controls, and high-contrast university palette.
- OBE/NAAC/NBA extension points: learning outcomes, criterion configuration, CO-PO mapping, and exportable audit history.

## Acceptance criteria

A seeded user can sign in, a faculty user can create and assign a practical, a student can submit a valid GitHub URL, and faculty can publish a grade that appears to the student and in the report export.
