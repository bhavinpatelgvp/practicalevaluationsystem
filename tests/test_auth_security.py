import pytest
from database import Base, SessionLocal, engine
from models import User, Role
from auth import (
    hash_password,
    create_password_reset,
    verify_password_reset,
    mark_password_reset_used,
)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        role = db.query(Role).filter_by(name="Student").first()
        if not role:
            role = Role(name="Student")
            db.add(role)
            db.commit()

        user = db.query(User).filter_by(username="security_test_user").first()
        if not user:
            user = User(
                username="security_test_user",
                full_name="Security Test User",
                email="security@example.com",
                password_hash=hash_password("Test@1234"),
                role_id=role.id,
            )
            db.add(user)
            db.commit()
    yield


def test_password_reset_hashing_and_invalidation():
    with SessionLocal() as db:
        user = db.query(User).filter_by(username="security_test_user").first()
        assert user is not None

        # 1. Create first password reset token
        pr1, raw_token1 = create_password_reset(db, user)
        db.commit()

        # Token stored in DB should NOT equal raw token (it is SHA-256 hashed)
        assert pr1.token != raw_token1
        assert len(pr1.token) == 64  # SHA-256 hex string length

        # 2. Verify raw token 1 resolves to user
        verified_user = verify_password_reset(db, raw_token1)
        assert verified_user is not None
        assert verified_user.id == user.id

        # 3. Create second password reset token (should invalidate first)
        pr2, raw_token2 = create_password_reset(db, user)
        db.commit()

        # Token 1 should now be invalidated/used
        assert verify_password_reset(db, raw_token1) is None

        # Token 2 should be valid
        assert verify_password_reset(db, raw_token2) is not None

        # 4. Mark token 2 as used
        mark_password_reset_used(db, raw_token2)
        db.commit()

        # Token 2 should no longer be valid
        assert verify_password_reset(db, raw_token2) is None
