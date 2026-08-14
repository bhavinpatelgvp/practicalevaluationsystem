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

    Looks for credentials in this priority order:
    1. st.secrets [admin] section  → [admin] email = "..." password = "..."
    2. st.secrets flat keys        → ADMIN_EMAIL / ADMIN_PASSWORD  (or admin / password)
    3. Environment variables       → ADMIN_EMAIL / ADMIN_PASSWORD in .env
    4. Raises RuntimeError with a setup guide
    """
    email = ""
    password = ""

    try:
        import streamlit as st
        if hasattr(st, "secrets") and st.secrets:
            sec = st.secrets

            # Pattern 1: nested [admin] section → [admin]\nemail = "..."\npassword = "..."
            if "admin" in sec and hasattr(sec["admin"], "get"):
                admin_sec = sec["admin"]
                email    = str(admin_sec.get("email",    "") or "").strip()
                password = str(admin_sec.get("password", "") or "").strip()

            # Pattern 2: flat ADMIN_EMAIL / ADMIN_PASSWORD keys
            if not email:
                email = str(sec.get("ADMIN_EMAIL", "") or "").strip()
            if not password:
                password = str(sec.get("ADMIN_PASSWORD", "") or "").strip()

            # Pattern 3: bare `admin = "email@..."` + `password = "..."` at top level
            if not email:
                candidate = str(sec.get("admin", "") or "").strip()
                # Only treat it as an email if it looks like one (contains @)
                if "@" in candidate:
                    email = candidate
            if not password:
                password = str(sec.get("password", "") or "").strip()

    except Exception:
        pass

    # Fallback: OS environment / .env
    if not email:
        email = os.getenv("ADMIN_EMAIL", "").strip()
    if not password:
        password = os.getenv("ADMIN_PASSWORD", "").strip()

    if not email or not password:
        raise RuntimeError(
            "\n\n"
            "┌─────────────────────────────────────────────────────┐\n"
            "│  ADMIN credentials are not configured.              │\n"
            "│                                                     │\n"
            "│  In .streamlit/secrets.toml (recommended):          │\n"
            "│    [admin]                                          │\n"
            "│    email    = \"admin@gujaratvidyapith.org\"          │\n"
            "│    password = \"YourStrongPassword@2025\"             │\n"
            "│                                                     │\n"
            "│  OR as flat keys in secrets.toml / .env:            │\n"
            "│    ADMIN_EMAIL=admin@gujaratvidyapith.org           │\n"
            "│    ADMIN_PASSWORD=YourStrongPassword@2025           │\n"
            "└─────────────────────────────────────────────────────┘\n"
        )

    return email, password


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
