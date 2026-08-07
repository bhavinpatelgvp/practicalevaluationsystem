import streamlit as st
from core.database import SessionLocal
from services.auth_service import authenticate, create_password_reset, verify_password_reset, mark_password_reset_used, hash_password
from core.rbac import has_permission
from services.email_service import send_html_email
from core.session_manager import create_session_token
from sqlalchemy import select
from models.schema import User
from datetime import datetime, timezone
import re

ROLE_OPTIONS = ["Administrator", "Faculty", "Student", "External Examiner", "Coordinator"]


def _trim(val: str) -> str:
    return val.strip() if isinstance(val, str) else val


def _is_valid_email(value: str) -> bool:
    if not value:
        return False
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value) is not None


def _rerun() -> None:
    try:
        st.experimental_rerun()
    except AttributeError:
        try:
            st.rerun()
        except AttributeError:
            pass


def render_login() -> None:
    # Layout: left branding, right auth form
    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("&nbsp;")
        st.image("assets/gujarat-vidyapith-logo.png", width=120)
        st.markdown("### Department of Computer Science")
        st.markdown("#### Practical Evaluation Management System")
        #st.write("- Transparent Evaluation\n- Digital Practical Submission\n- Grade Analytics\n- Faculty Dashboard\n- Student Progress Tracking")
    with right:
        #st.markdown("<div class='login-card'>", unsafe_allow_html=True)
        st.markdown("&nbsp;")
        st.markdown("### Sign in")
        with st.form("loginform"):
            username = _trim(st.text_input("Username or Email", placeholder="username or email"))
            password = st.text_input("Password", type="password")
            role = st.selectbox("Role", options=["Select Role"] + ROLE_OPTIONS, index=0)
            remember = st.checkbox("Remember me")
            cols = st.columns([3, 1])
            with cols[0]:
                submitted = st.form_submit_button("Sign in")
            with cols[1]:
                st.markdown("&nbsp;")
            if submitted:
                # validations
                if not username:
                    st.error("Username is required.")
                elif not password:
                    st.error("Password is required.")
                elif role == "Select Role":
                    st.error("Please select your role.")
                else:
                    with SessionLocal() as db:
                        user = authenticate(db, username, password, role_name=role)
                        if not user:
                            st.error("Invalid credentials.")
                        else:
                            # check permission for selected role
                            if role != "Administrator" and not has_permission(db, user, f"{role.lower()}.access"):
                                st.error("You are not permitted to sign in for the selected role.")
                                return
                            st.success("Login Successful. Redirecting to your dashboard...")
                            st.session_state.user_id = user.id
                            st.session_state.name = user.full_name
                            st.session_state.role = user.role.name
                            st.session_state.email = user.email
                            st.session_state.department = getattr(user, 'department', None)
                            st.session_state.login_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
                            st.query_params["session"] = create_session_token(user.id, user.role.name)

                            _rerun()
        #st.markdown("</div>", unsafe_allow_html=True)

        # Help button outside the form (forms do not allow st.button)
        #if st.button("Help"):
            #st.info("For assistance, contact the system administrator or consult the user manual.")

        #st.markdown("---")
        # Forgot password
        if st.checkbox("Forgot password?"):
            with st.form("forgot"):
                identifier = _trim(st.text_input("Username or Email"))
                if st.form_submit_button("Send reset link"):
                    if not identifier:
                        st.error("Please provide username or email.")
                    else:
                        with SessionLocal() as db:
                            user = db.scalar(select(User).where((User.username == identifier) | (User.email == identifier)))
                            if not user:
                                st.info("If the account exists, a reset link has been sent.")
                            else:
                                pr, raw_token = create_password_reset(db, user)
                                db.commit()
                                # use a relative reset link query parameter; Streamlit URL building differs by deployment
                                reset_url = f"?reset={raw_token}"

                                html = f"<p>Click the link to reset your password (valid for 30 minutes): <a href='{reset_url}'>Reset password</a></p>"
                                try:
                                    send_html_email(user.email, "Password reset for TPEMS", html)
                                    st.success("If the account exists, a reset link has been sent.")
                                except Exception:
                                    st.error("Failed to send email — check SMTP settings.")


def handle_reset(token: str) -> None:
    with SessionLocal() as db:
        user = verify_password_reset(db, token)
        if not user:
            st.error("Invalid or expired token.")
            return
        with st.form("resetform"):
            pwd = st.text_input("New password", type="password")
            pwd2 = st.text_input("Confirm password", type="password")
            if st.form_submit_button("Reset password"):
                if not pwd or not pwd2:
                    st.error("Password fields are required.")
                elif pwd != pwd2:
                    st.error("Passwords do not match.")
                else:
                    # basic policy
                    if len(pwd) < 8 or not re.search(r"[A-Z]", pwd) or not re.search(r"[a-z]", pwd) or not re.search(r"\d", pwd) or not re.search(r"[^A-Za-z0-9]", pwd):
                        st.error("Password does not meet policy requirements.")
                        return
                    user.password_hash = hash_password(pwd)
                    db.add(user)
                    mark_password_reset_used(db, token)
                    db.commit()
                    st.success("Password updated. Please sign in with your new password.")


if __name__ == "__main__":
    render_login()
