"""Seed script — safe to commit to a public repository.

Admin credentials are read from st.secrets / environment variables at runtime.
No passwords or sensitive values are ever hardcoded here.

Local development
-----------------
Add to .env (already gitignored):
    ADMIN_EMAIL=admin@gujaratvidyapith.org
    ADMIN_PASSWORD=YourStrongPassword@2025

Streamlit Community Cloud
--------------------------
Add to App Secrets (Settings → Secrets):
    [admin]
    email    = "admin@gujaratvidyapith.org"
    password = "YourStrongPassword@2025"
"""
import sys
from core.config import _get_setting
from core.database import SessionLocal, init_db
from services.core_services import ensure_role, ensure_permission, grant_role_permission
from services.auth_service import hash_password
from models.schema import Department, Program, Role, User

LOGIN_ROLES = ["Administrator", "Faculty", "Student", "External Examiner", "Coordinator"]

# permission_code → (description, list of role names that should receive it)
CORE_PERMISSIONS = {
    "admin.access":   ("Access administrator workspace and management features", ["Administrator"]),
    "faculty.access": ("Access the faculty workspace and manage assigned subjects", ["Administrator", "Faculty"]),
    "student.access": ("Access the student practicals and dashboard views", ["Administrator", "Student"]),
}


def _resolve_admin_credentials() -> tuple[str, str]:
    """Return (email, password) from secrets/env — never from hardcoded values.

    Priority:
    1. st.secrets [admin] section  → used on Streamlit Community Cloud
    2. ADMIN_EMAIL / ADMIN_PASSWORD environment variables  → used locally via .env
    3. Raise RuntimeError so the app fails loudly instead of creating insecure defaults.
    """
    # Try nested st.secrets [admin] section first
    email    = _get_setting("ADMIN_EMAIL", "")
    password = _get_setting("ADMIN_PASSWORD", "")

    # Also try the nested [admin] section directly (st.secrets["admin"]["email"])
    if not email or not password:
        try:
            import streamlit as st
            if hasattr(st, "secrets") and "admin" in st.secrets:
                admin_sec = st.secrets["admin"]
                email    = email    or str(admin_sec.get("email",    ""))
                password = password or str(admin_sec.get("password", ""))
        except Exception:
            pass

    if not email or not password:
        raise RuntimeError(
            "\n\n"
            "┌─────────────────────────────────────────────────────┐\n"
            "│  ADMIN credentials are not configured.              │\n"
            "│                                                     │\n"
            "│  Local dev — add to .env:                           │\n"
            "│    ADMIN_EMAIL=admindemo@gujaratvidyapith.org       │\n"
            "│    ADMIN_PASSWORD=Admin@Demo                        │\n"
            "│                                                     │\n"
            "│  Streamlit Cloud — add to App Secrets:              │\n"
            "│    [admin]                                          │\n"
            "│    email    = \"admindemo@gujaratvidyapith.org \"   │\n"
            "│    password = \"Admin@12023\"                       │\n"
            "└─────────────────────────────────────────────────────┘\n"
        )

    return email.strip(), password.strip()


def seed() -> None:
    init_db()
    with SessionLocal() as db:
        # 1. Seed RBAC roles (idempotent)
        roles = {name: ensure_role(db, name) for name in LOGIN_ROLES}

        # 2. Seed RBAC permissions and grant to roles (idempotent)
        for code, (description, role_names) in CORE_PERMISSIONS.items():
            perm = ensure_permission(db, code, description)
            for role_name in role_names:
                grant_role_permission(db, roles[role_name], perm)
        db.commit()
        print("Permissions synced:", ", ".join(CORE_PERMISSIONS))

        # 3. Seed default base Department & Program if not existing
        department = db.query(Department).filter_by(code="CS").first()
        if not department:
            department = Department(name="Department of Computer Science", code="CS")
            db.add(department)
            db.flush()

        program = db.query(Program).filter_by(code="MCA").first()
        if not program:
            program = Program(
                code="MCA",
                name="Master of Computer Applications",
                duration_months=24,
                total_semesters=4,
                department=department,
            )
            db.add(program)
            db.flush()

        # 4. Seed ONLY ONE Administrator — credentials from secrets/env only
        admin_role = roles["Administrator"]
        existing_admin = db.query(User).filter_by(role_id=admin_role.id).first()
        if existing_admin:
            print(f"Administrator already exists: {existing_admin.username} ({existing_admin.email})")
            db.commit()
            return

        admin_email, admin_password = _resolve_admin_credentials()

        admin = User(
            username=admin_email,
            full_name="System Administrator",
            email=admin_email,
            password_hash=hash_password(admin_password),
            role=admin_role,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        # Never print the password — only confirm the email was used
        print(f"Administrator seeded successfully: {admin_email}")


if __name__ == "__main__":
    try:
        seed()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
