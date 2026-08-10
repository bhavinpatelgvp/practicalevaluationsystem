import urllib.parse
import requests
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from core.config import settings
from models.schema import User
from services.auth_service import record_login, reset_failed_attempts, utc_now

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"


def is_google_auth_configured() -> bool:
    """Return True if Google OAuth client ID and secret are configured."""
    return bool(settings.google_client_id and settings.google_client_secret)


def get_google_auth_url(state: str | None = None) -> str:
    """Generate Google OAuth 2.0 authorization URL."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    if settings.google_hosted_domain:
        params["hd"] = settings.google_hosted_domain
    if state:
        params["state"] = state
    return f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def exchange_code_for_user_info(code: str, redirect_uri: str | None = None) -> tuple[dict | None, str | None]:
    """Exchange authorization code for Google user profile information.
    
    Returns (user_info_dict, error_message).
    """
    if not is_google_auth_configured():
        return None, "Google OAuth is not configured. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
    
    redirect = redirect_uri or settings.google_redirect_uri
    payload = {
        "client_id": settings.google_client_id,
        "client_secret": settings.google_client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect,
    }
    try:
        response = requests.post(GOOGLE_TOKEN_ENDPOINT, data=payload, timeout=10)
        if response.status_code != 200:
            try:
                err_data = response.json()
                err_desc = err_data.get("error_description") or err_data.get("error") or response.text
            except Exception:
                err_desc = response.text
            return None, f"Google OAuth Error ({response.status_code}): {err_desc}"
        token_data = response.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return None, "Google returned a success response but no access token was found."

        userinfo_resp = requests.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if userinfo_resp.status_code != 200:
            return None, f"Failed to fetch Google profile info ({userinfo_resp.status_code}): {userinfo_resp.text}"
        return userinfo_resp.json(), None
    except Exception as e:
        return None, f"Connection error contacting Google OAuth: {str(e)}"


import secrets
from models.schema import Program, Student, User
from services.auth_service import ensure_role, hash_password, record_login, reset_failed_attempts, utc_now


def authenticate_google_user(db: Session, google_info: dict, ip: str | None = None) -> tuple[User | None, str | None]:
    """Authenticate or verify a user from Google profile info.
    
    If the user does not exist, auto-provisions a new account with:
    - username = email
    - default role = Student
    - linked Student profile
    """
    email = (google_info.get("email") or "").strip()
    if not email:
        return None, "Google account does not provide an email address."

    # Domain restriction check if configured
    if settings.google_hosted_domain:
        required_suffix = f"@{settings.google_hosted_domain.lower()}"
        if not email.lower().endswith(required_suffix):
            return None, f"Only @{settings.google_hosted_domain} institutional accounts are permitted to sign in."

    user = db.scalar(select(User).where((func.lower(User.email) == email.lower()) | (func.lower(User.username) == email.lower())))
    
    if not user:
        # Auto-create new user with email as username and default role as Student
        student_role = ensure_role(db, "Student")
        full_name = (google_info.get("name") or email.split("@")[0]).strip()
        user = User(
            username=email.lower(),
            full_name=full_name,
            email=email.lower(),
            password_hash=hash_password(secrets.token_urlsafe(16)),
            role_id=student_role.id,
            is_active=True,
        )
        db.add(user)
        db.flush()

        # Create linked Student profile
        first_prog = db.scalar(select(Program).order_by(Program.id))
        enrollment_no = email.split("@")[0]
        existing_stud = db.scalar(select(Student).where(Student.enrollment_no == enrollment_no))
        if existing_stud:
            enrollment_no = f"{enrollment_no}_{user.id}"

        student_profile = Student(
            user_id=user.id,
            enrollment_no=enrollment_no,
            semester=1,
            program=first_prog.code if first_prog else "MCA",
            program_id=first_prog.id if first_prog else None,
        )
        db.add(student_profile)
        db.flush()

    if not user.is_active:
        record_login(db, user, email, user.role.name if user.role else None, "failed:account-inactive", ip)
        db.commit()
        return None, "Your account has been deactivated. Please contact the administrator."

    if user.account_locked:
        record_login(db, user, email, user.role.name if user.role else None, "failed:account-locked", ip)
        db.commit()
        return None, "Your account is locked due to too many failed attempts. Please contact the administrator."

    # Successful login
    reset_failed_attempts(db, user)
    user.last_login = utc_now()
    db.add(user)
    record_login(db, user, user.username, user.role.name if user.role else None, "success:google-oauth", ip)
    db.commit()
    return user, None
