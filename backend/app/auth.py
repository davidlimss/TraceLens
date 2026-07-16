import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.models import Case, CaseMembership, User, UserSession

SESSION_COOKIE = "tracelens_session"
CSRF_COOKIE = "tracelens_csrf"
PBKDF2_ITERATIONS = 310_000
ROLE_PERMISSIONS = {
    "viewer": {"read"},
    "investigator": {"read", "upload", "chat", "export"},
    "reviewer": {"read", "export"},
    "admin": {"read", "upload", "chat", "export", "admin"},
}


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def create_session(db: Session, user: User, settings: Settings) -> tuple[str, str, UserSession]:
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session = UserSession(user_id=user.user_id, token_hash=token_hash(token), csrf_hash=token_hash(csrf),
                          expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours))
    db.add(session)
    return token, csrf, session


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "authentication_required", "message": "Login required"})
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(token),
                                                  UserSession.expires_at > datetime.now(timezone.utc)))
    user = db.get(User, session.user_id) if session else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail={"code": "invalid_session", "message": "Session is invalid or expired"})
    request.state.user = user
    request.state.session = session
    return user


def require_csrf(request: Request, user: User = Depends(get_current_user)) -> User:
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        supplied = request.headers.get("X-CSRF-Token", "")
        cookie = request.cookies.get(CSRF_COOKIE, "")
        session = request.state.session
        if not supplied or not cookie or not hmac.compare_digest(supplied, cookie) or not hmac.compare_digest(token_hash(supplied), session.csrf_hash):
            raise HTTPException(status_code=403, detail={"code": "csrf_failed", "message": "CSRF validation failed"})
    return user


def require_case_permission(permission: str):
    def dependency(case_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> User:
        if db.get(Case, case_id) is None:
            raise HTTPException(status_code=404, detail={"code": "case_not_found", "message": "Case not found"})
        if user.global_role == "admin":
            return user
        membership = db.scalar(select(CaseMembership).where(CaseMembership.case_id == case_id,
                                                             CaseMembership.user_id == user.user_id))
        if membership is None or permission not in ROLE_PERMISSIONS.get(membership.role, set()):
            raise HTTPException(status_code=403, detail={"code": "case_access_denied", "message": "Access to this case is denied"})
        return user
    return dependency
