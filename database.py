from collections.abc import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from config import settings


class Base(DeclarativeBase):
    pass


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    from models import all_models  # noqa: F401
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        practical_columns = {column["name"] for column in inspect(engine).get_columns("practicals")}
        if "submission_date" not in practical_columns:
            connection.execute(text("ALTER TABLE practicals ADD COLUMN submission_date DATE"))
        if "grade" not in practical_columns:
            connection.execute(text("ALTER TABLE practicals ADD COLUMN grade VARCHAR(3) DEFAULT 'A'"))

        if inspect(engine).has_table("users"):
            user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
            if "last_login" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN last_login DATETIME"))
            if "failed_attempts" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN failed_attempts INTEGER DEFAULT 0"))
            if "account_locked" not in user_columns:
                connection.execute(text("ALTER TABLE users ADD COLUMN account_locked BOOLEAN DEFAULT 0"))


def get_db() -> Generator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
