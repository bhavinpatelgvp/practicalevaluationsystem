from core.database import SessionLocal, init_db
from services.core_services import ensure_role, ensure_permission, grant_role_permission
from services.auth_service import hash_password
from models.schema import Department, Program, Role, User

LOGIN_ROLES = ["Administrator", "Faculty", "Student", "External Examiner", "Coordinator"]

# permission_code -> (description, list of role names that should receive it)
CORE_PERMISSIONS = {
    "admin.access": ("Access administrator workspace and management features", ["Administrator"]),
    "faculty.access": ("Access the faculty workspace and manage assigned subjects", ["Administrator", "Faculty"]),
    "student.access": ("Access the student practicals and dashboard views", ["Administrator", "Student"]),
}


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

        # 4. Seed ONLY ONE Administrator user
        admin_role = roles["Administrator"]
        existing_admin = db.query(User).filter_by(role_id=admin_role.id).first()
        if existing_admin:
            print(f"Administrator already exists: {existing_admin.username} ({existing_admin.email})")
            db.commit()
            return

        admin = User(
            username="admin@gujaratvidyapith.org",
            full_name="System Administrator",
            email="admin@gujaratvidyapith.org",
            password_hash=hash_password("Admin@123"),
            role=admin_role,
            is_active=True,
        )
        db.add(admin)
        db.commit()
        print("Successfully seeded 1 Administrator: admin@gujaratvidyapith.org / Admin@123")


if __name__ == "__main__":
    seed()
