import bcrypt
import hashlib
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Role, User, LoginLog, PasswordReset
from datetime import datetime, timedelta, timezone
import secrets

def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def ensure_role(db, role_name: str):
    # lazy import to avoid circular dependency between auth and services
    from services import ensure_role as _ensure_role

    return _ensure_role(db, role_name)


MAX_FAILED_ATTEMPTS = 5
RESET_TOKEN_TTL_MINUTES = 30


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception:
        return False


def record_login(db: Session, user: User | None, username: str, role: str | None, status: str, ip: str | None = None, browser: str | None = None, os: str | None = None) -> None:
    log = LoginLog(
        user_id=user.id if user else None,
        username=username,
        role=role,
        login_time=utc_now(),
        ip_address=ip,
        browser=browser,
        os=os,
        status=status,
    )
    db.add(log)


def reset_failed_attempts(db: Session, user: User) -> None:
    user.failed_attempts = 0
    user.account_locked = False
    db.add(user)


def authenticate(db: Session, username_or_email: str, password: str, role_name: str | None = None, ip: str | None = None, browser: str | None = None, os: str | None = None) -> User | None:
    # find by username or email
    user = db.scalar(select(User).where((User.username == username_or_email) | (User.email == username_or_email)))
    if not user or not user.is_active:
        record_login(db, user, username_or_email, role_name, "failed:invalid-credentials", ip, browser, os)
        return None
    if user.account_locked:
        record_login(db, user, username_or_email, role_name, "failed:account-locked", ip, browser, os)
        return None
    if not verify_password(password, user.password_hash):
        user.failed_attempts = (user.failed_attempts or 0) + 1
        status = "failed:invalid-credentials"
        if user.failed_attempts >= MAX_FAILED_ATTEMPTS:
            user.account_locked = True
            status = "failed:account-locked"
        db.add(user)
        record_login(db, user, username_or_email, role_name, status, ip, browser, os)
        return None
    # password correct
    # check role if provided
    if role_name:
        role = db.scalar(select(Role).where(Role.id == user.role_id))
        if not role or role.name.lower() != role_name.lower():
            record_login(db, user, username_or_email, role_name, "failed:role-mismatch", ip, browser, os)
            return None
    # success
    reset_failed_attempts(db, user)
    user.last_login = utc_now()
    db.add(user)
    record_login(db, user, username_or_email, role_name, "success", ip, browser, os)
    return user


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_password_reset(db: Session, user: User) -> tuple[PasswordReset, str]:
    # Invalidate previous unused reset tokens for this user
    existing = db.scalars(select(PasswordReset).where(PasswordReset.user_id == user.id, PasswordReset.used.is_(False))).all()
    for old_pr in existing:
        old_pr.used = True
        db.add(old_pr)

    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    now = utc_now()
    expires = now + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    pr = PasswordReset(user_id=user.id, token=token_hash, created_at=now, expires_at=expires, used=False)
    db.add(pr)
    return pr, raw_token


def verify_password_reset(db: Session, token: str) -> User | None:
    token_hash = _hash_token(token)
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token == token_hash, PasswordReset.used.is_(False)))
    if not pr:
        return None
    if pr.expires_at < utc_now():
        return None
    user = db.get(User, pr.user_id)
    return user


def mark_password_reset_used(db: Session, token: str) -> None:
    token_hash = _hash_token(token)
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token == token_hash))
    if pr:
        pr.used = True
        db.add(pr)

