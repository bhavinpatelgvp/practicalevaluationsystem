from sqlalchemy import select
from sqlalchemy.orm import Session
from models import Permission, Role, RolePermission


def has_permission(db: Session, user, permission_code: str) -> bool:
    """Return True if the user's role includes the permission_code."""
    if not user or not getattr(user, "role_id", None):
        return False
    role = db.get(Role, user.role_id)
    if not role:
        return False
    perm = db.scalar(select(Permission).where(Permission.code == permission_code))
    if not perm:
        return False
    link = db.scalar(select(RolePermission).where(RolePermission.role_id == role.id, RolePermission.permission_id == perm.id))
    return link is not None

