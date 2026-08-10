from dataclasses import dataclass
import os
import warnings


def _parse_env_line(line: str) -> tuple[str, str] | None:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None
    key, val = line.split("=", 1)
    key = key.strip()
    val = val.strip()

    if val.startswith('"'):
        end_idx = val.find('"', 1)
        if end_idx != -1:
            val = val[1:end_idx]
        else:
            val = val.strip('"')
    elif val.startswith("'"):
        end_idx = val.find("'", 1)
        if end_idx != -1:
            val = val[1:end_idx]
        else:
            val = val.strip("'")
    else:
        if "#" in val:
            val = val.split("#", 1)[0].strip()
    return key, val


def _load_env_file() -> None:
    """Load key-value pairs from .env file into os.environ if present."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(base_dir, ".env"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        parsed = _parse_env_line(line)
                        if parsed:
                            key, val = parsed
                            # Overwrite or set in environ
                            os.environ[key] = val
            except Exception:
                pass
            break


_load_env_file()


def _get_setting(key: str, default: str = "") -> str:
    """Get setting from environment / .env, with fallback to Streamlit secrets."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return default


@dataclass(frozen=True)
class Settings:
    database_url: str = _get_setting("DATABASE_URL", "sqlite:///tpems.db")
    secret_key: str = _get_setting("SECRET_KEY", "development-only-change-me")
    smtp_host: str = _get_setting("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(_get_setting("SMTP_PORT", "587"))
    smtp_user: str = _get_setting("SMTP_USER", "")
    smtp_password: str = _get_setting("SMTP_PASSWORD", "")
    mail_from: str = _get_setting("MAIL_FROM", "")
    session_timeout_minutes: int = int(_get_setting("SESSION_TIMEOUT_MINUTES", "60"))
    google_client_id: str = _get_setting("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = _get_setting("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = _get_setting("GOOGLE_REDIRECT_URI", "http://localhost:8501")
    google_hosted_domain: str = _get_setting("GOOGLE_HOSTED_DOMAIN", "")  # e.g. gujaratvidyapith.org


def load_settings() -> Settings:
    """Reload and return fresh Settings instance."""
    _load_env_file()
    return Settings()


settings = load_settings()

if settings.secret_key == "development-only-change-me":
    warnings.warn(
        "SECRET_KEY is set to the default development key. Please configure SECRET_KEY in your environment for production.",
        UserWarning,
    )


