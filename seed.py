from datetime import date, timedelta
from database import SessionLocal, init_db
from auth import ensure_role, hash_password
from models import Department, FacultySubject, Practical, Student, Subject, User


def seed() -> None:
    init_db()
    with SessionLocal() as db:
        if db.query(User).first():
            print("Database already contains data")
            return
        roles = {name: ensure_role(db, name) for name in ["Administrator", "Faculty", "Student"]}
        department = Department(name="Computer Science", code="CS")
        db.add(department); db.flush()
        admin = User(username="admin", full_name="System Administrator", email="admin@gujaratvidyapith.org", password_hash=hash_password("Admin@123"), role=roles["Administrator"])
        faculty = User(username="faculty", full_name="Dr. Asha Patel", email="faculty@gujaratvidyapith.org", password_hash=hash_password("Faculty@123"), role=roles["Faculty"])
        db.add_all([admin, faculty]); db.flush()
        subject = Subject(code="CS301", name="Advanced Programming Lab", semester=3, department=department)
        db.add(subject); db.flush()
        db.add(FacultySubject(faculty_id=faculty.id, subject_id=subject.id, assigned_by=admin.id))
        practical = Practical(subject=subject, practical_number=1, title="Repository-based application", description="Build and document a small application.", learning_outcome="Apply software engineering practices.", created_by=faculty.id, submission_date=date.today() + timedelta(days=14))
        db.add(practical)
        for index in range(1, 11):
            user = User(username=f"student{index}", full_name=f"Student {index}", email=f"student{index}@gujaratvidyapith.org", password_hash=hash_password("Student@123"), role=roles["Student"])
            db.add(user); db.flush()
            db.add(Student(user=user, enrollment_no=f"GVCS23{index:03d}", semester=3, program="MCA"))
        db.commit()
        print("Seeded: admin/Admin@123, faculty/Faculty@123 (subject CS301 assigned), student1/Student@123")


if __name__ == "__main__":
    seed()
