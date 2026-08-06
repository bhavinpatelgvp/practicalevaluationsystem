# Architecture

```mermaid
flowchart LR
  Browser[Streamlit browser] --> UI[Role dashboards]
  UI --> Services[Application services]
  Services --> ORM[SQLAlchemy ORM]
  ORM --> DB[(MySQL 8 / SQLite dev)]
  Services --> Audit[(Audit logs)]
  Services --> Mail[SMTP adapter]
  Reports[PDF/XLSX exporter] --> ORM
```

The UI is deliberately thin. Domain transitions live in `services.py`, persistence is represented by `models.py`, and configuration is environment-based. Email, GitHub API validation, scheduled reminders, and background jobs should be introduced as adapters around the service boundary.

## Core sequence

```mermaid
sequenceDiagram
  participant F as Faculty
  participant S as Streamlit
  participant DB as Database
  participant T as Student
  F->>S: Create practical
  S->>DB: Persist practical
  F->>S: Assign practical
  S->>DB: Create one assignment per student
  T->>S: Submit GitHub URL
  S->>DB: Validate and persist submission
  F->>S: Enter criterion marks
  S->>DB: Publish evaluation and audit event
```

## ER overview

```mermaid
erDiagram
  ROLE ||--o{ USER : grants
  USER ||--o| STUDENT : profiles
  DEPARTMENT ||--o{ SUBJECT : owns
  USER ||--o{ FACULTY_SUBJECT : teaches
  SUBJECT ||--o{ FACULTY_SUBJECT : taught_by
  SUBJECT ||--o{ PRACTICAL : contains
  PRACTICAL ||--o{ ASSIGNMENT : creates
  STUDENT ||--o{ ASSIGNMENT : receives
  ASSIGNMENT ||--o| SUBMISSION : has
  SUBMISSION ||--o| EVALUATION : receives
  USER ||--o{ AUDIT_LOG : performs
```
