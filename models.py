from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), unique=True)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    subjects: Mapped[list["Subject"]] = relationship(back_populates="department")


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    account_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[Role] = relationship(back_populates="users")
    student: Mapped["Student | None"] = relationship(back_populates="user", uselist=False)
    faculty_subjects: Mapped[list["FacultySubject"]] = relationship(
        back_populates="faculty", foreign_keys="FacultySubject.faculty_id"
    )


class Student(Base):
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    enrollment_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    semester: Mapped[int] = mapped_column(Integer)
    program: Mapped[str] = mapped_column(String(80), default="MCA")
    user: Mapped[User] = relationship(back_populates="student")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="student")


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(150))
    semester: Mapped[int] = mapped_column(Integer)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"))
    department: Mapped[Department] = relationship(back_populates="subjects")
    practicals: Mapped[list["Practical"]] = relationship(back_populates="subject")
    faculty_subjects: Mapped[list["FacultySubject"]] = relationship(
        back_populates="subject", foreign_keys="FacultySubject.subject_id"
    )


class FacultySubject(Base):
    __tablename__ = "faculty_subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    faculty: Mapped[User] = relationship(back_populates="faculty_subjects", foreign_keys=[faculty_id])
    subject: Mapped[Subject] = relationship(back_populates="faculty_subjects", foreign_keys=[subject_id])
    __table_args__ = (UniqueConstraint("faculty_id", "subject_id"),)


class Practical(Base):
    __tablename__ = "practicals"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"), index=True)
    practical_number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    learning_outcome: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str] = mapped_column(String(20), default="Medium")
    max_marks: Mapped[int] = mapped_column(Integer, default=100)
    grade: Mapped[str] = mapped_column(String(3), default="A")
    submission_days: Mapped[int] = mapped_column(Integer, default=7)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    subject: Mapped[Subject] = relationship(back_populates="practicals")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="practical", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("subject_id", "practical_number"),)


class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    practical_id: Mapped[int] = mapped_column(ForeignKey("practicals.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    deadline: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(25), default="Assigned")
    practical: Mapped[Practical] = relationship(back_populates="assignments")
    student: Mapped[Student] = relationship(back_populates="assignments")
    submission: Mapped["Submission | None"] = relationship(back_populates="assignment", uselist=False, cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("practical_id", "student_id"), Index("ix_assignment_status", "status"))


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("assignments.id"), unique=True)
    github_url: Mapped[str] = mapped_column(String(500))
    commit_hash: Mapped[str] = mapped_column(String(100), default="")
    branch: Mapped[str] = mapped_column(String(100), default="main")
    documentation: Mapped[str] = mapped_column(Text, default="")
    remarks: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False)
    assignment: Mapped[Assignment] = relationship(back_populates="submission")
    evaluation: Mapped["Evaluation | None"] = relationship(back_populates="submission", uselist=False, cascade="all, delete-orphan")


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id"), unique=True)
    evaluator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    code_quality: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    logic: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    output: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    documentation: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    git_usage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    innovation: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    total_marks: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    grade: Mapped[str] = mapped_column(String(3), default="F")
    remarks: Mapped[str] = mapped_column(Text, default="")
    suggestions: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submission: Mapped[Submission] = relationship(back_populates="evaluation")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class LoginLog(Base):
    __tablename__ = "login_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    role: Mapped[str | None] = mapped_column(String(60), nullable=True)
    login_time: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    logout_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(200), nullable=True)
    os: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="failed")


class PasswordReset(Base):
    __tablename__ = "password_resets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


all_models = (
    Role,
    Department,
    User,
    Student,
    Subject,
    FacultySubject,
    Practical,
    Assignment,
    Submission,
    Evaluation,
    AuditLog,
    LoginLog,
    PasswordReset,
)
