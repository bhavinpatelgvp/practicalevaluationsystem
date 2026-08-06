# TPEMS

Transparent Practical Evaluation & Monitoring System for the Department of Computer Science, Gujarat Vidyapith.

## What is included

This repository contains a runnable Streamlit MVP with a production-shaped boundary:

- Role-based login for Administrator, Faculty, and Student.
- SQLAlchemy 2 ORM with MySQL 8 support and SQLite development fallback.
- Practical creation, bulk assignment, deadline tracking, GitHub URL submission, duplicate-safe editing, late status, evaluation, automatic grade calculation, and audit logs.
- Plotly dashboard, marks export to Excel/PDF, and deterministic seed data.
- Docker packaging, focused tests, architecture/SRS/security/deployment documentation.

The system intentionally keeps repository validation URL-based in this first release. GitHub API checks for README, branch, and repository contents belong behind a configured GitHub App/token in a later integration, rather than being guessed from an unauthenticated URL.

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python seed.py
.venv\Scripts\streamlit run app.py
```

Demo accounts after seeding:

- `admin` / `Admin@123`
- `faculty` / `Faculty@123`
- `student1` / `Student@123`

Change all demo passwords before deployment. For MySQL, set `DATABASE_URL=mysql+pymysql://user:password@host:3306/tpems`.

## Production checklist

Use a secrets manager for `SECRET_KEY`, SMTP credentials, and the database URL. Put Streamlit behind HTTPS and an identity-aware reverse proxy, use Alembic migrations instead of `create_all`, configure scheduled reminders, add a GitHub App for repository checks, and back up MySQL with encrypted off-site retention. See [docs/deployment.md](docs/deployment.md) and [docs/security.md](docs/security.md).
