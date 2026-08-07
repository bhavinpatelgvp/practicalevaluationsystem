from datetime import datetime, timezone
import streamlit as st
from core.database import SessionLocal, init_db, run_migrations
from ui.auth import render_login, handle_reset
from models.schema import User
from ui.admin import administrator_page
from ui.faculty import faculty_page
from ui.dashboard import dashboard, student_dashboard
from ui.student import student_page
from core.config import settings
from core.session_manager import verify_session_token
from core.logger import get_logger

logger = get_logger(__name__)

from ui.theme import apply_theme

st.set_page_config(page_title="TPEMS | Gujarat Vidyapith", page_icon="🎓", layout="wide")
apply_theme()




def render_brand_header() -> None:
  return None


def render_footer() -> None:
    st.markdown(
        """
        <div class="page-footer">
            🎓&nbsp; <strong>Gujarat Vidyapith</strong>
            &nbsp;·&nbsp; Designed for Department of Computer Science
            &nbsp;&nbsp;|&nbsp;&nbsp;
            &copy; 2026 Gujarat Vidyapith &nbsp;·&nbsp; Practical Evaluation &amp; Management System
        </div>
        """,
        unsafe_allow_html=True,
    )


run_migrations()
if "user_id" not in st.session_state:

    st.session_state.user_id = None


def login() -> None:
    render_login()






with SessionLocal() as db:
    # Restore session from signed query token on browser reload if present
    if not st.session_state.get("user_id"):
        session_token = st.query_params.get("session")
        if session_token:
            payload = verify_session_token(session_token)
            if payload:
                restored_user = db.get(User, payload["user_id"])
                if restored_user and restored_user.is_active and not restored_user.account_locked:
                    logger.info("Session restored from query token", extra={"user_id": restored_user.id, "role": restored_user.role.name})
                    st.session_state.user_id = restored_user.id
                    st.session_state.name = restored_user.full_name
                    st.session_state.role = restored_user.role.name
                    st.session_state.email = restored_user.email
                    st.session_state.department = getattr(restored_user, 'department', None)
                    st.session_state.login_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
            else:
                st.query_params.clear()

    if not st.session_state.get("user_id"):
      # handle password reset token in query params
      def _get_query_params():
        return st.query_params

      params = _get_query_params()
      if "reset" in params:
        handle_reset(params.get("reset"))
      else:
        render_login()
    else:
        login_time_str = st.session_state.get("login_time")
        if login_time_str:
            try:
                login_time = datetime.fromisoformat(login_time_str)
                if (datetime.now(timezone.utc).replace(tzinfo=None) - login_time).total_seconds() > settings.session_timeout_minutes * 60:
                    logger.info("Session timed out due to inactivity", extra={"user_id": st.session_state.get("user_id")})
                    st.session_state.clear()
                    st.query_params.clear()
                    st.warning("Your session has timed out due to inactivity. Please sign in again.")
                    st.rerun()
            except Exception:
                pass
        user = db.get(User, st.session_state.user_id)
        if not user:
            st.session_state.user_id = None
            st.query_params.clear()
            st.rerun()
      # brand header removed
        with st.sidebar:
          st.markdown("**Transparent Practical Evaluation**")
          st.caption(f"{user.full_name} · {user.role.name}")
          if user.role.name == "Administrator":
            workspace_options = ["Dashboard", "Administration"]
            welcome = "Manages master data, faculty, and users."
          elif user.role.name == "Faculty":
            workspace_options = ["My subjects"]
            welcome = "Works within the subjects assigned to you."
          else:
            workspace_options = ["Dashboard", "Practicals"]
            welcome = ""
          if welcome:
            st.caption(welcome)
          st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)
          page = st.radio("Workspace", workspace_options, label_visibility="visible")
          st.markdown("---")

          if st.button("Sign out"):
            logger.info("User signed out", extra={"user_id": st.session_state.get("user_id")})
            st.session_state.clear()
            st.query_params.clear()
            st.rerun()

          st.markdown(
            """
            <div class="sidebar-footer">
              <div class="sidebar-footer-divider"></div>
              <div class="sidebar-footer-brand">🎓 Gujarat Vidyapith</div>
              <div class="sidebar-footer-sub">Dept. of Computer Science</div>
              <div class="sidebar-footer-copy">© 2026 · Practical Evaluation System</div>
            </div>
            """,
            unsafe_allow_html=True,
          )
        if page == "Dashboard" and user.role.name == "Student" and user.student:
            student_dashboard(db, user.student)
        elif page == "Dashboard":
            dashboard(db, user)
        elif page == "Administration" and user.role.name == "Administrator":
            administrator_page(db, user)
        elif page == "My subjects" and user.role.name == "Faculty":
            faculty_page(db, user)
        elif user.role.name == "Student" and user.student:
            student_page(db, user.student)
        else:
            st.error("No student profile is linked to this account.")
        render_footer()
