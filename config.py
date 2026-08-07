from dataclasses import dataclass
import os


import warnings


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///tpems.db")
    secret_key: str = os.getenv("SECRET_KEY", "development-only-change-me")
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    mail_from: str = os.getenv("MAIL_FROM", "")
    session_timeout_minutes: int = int(os.getenv("SESSION_TIMEOUT_MINUTES", "60"))


settings = Settings()

if settings.secret_key == "development-only-change-me":
    warnings.warn(
        "SECRET_KEY is set to the default development key. Please configure SECRET_KEY in your environment for production.",
        UserWarning,
    )

