"""Password hashing and opaque server-side browser sessions."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SessionRecord, User
from .config import SETTINGS


PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=2, hash_len=32, salt_len=16)
SESSION_COOKIE = "gs_session"
CSRF_COOKIE = "gs_csrf"
SESSION_HOURS = SETTINGS.session_hours
COOKIE_SECURE = SETTINGS.app_env == "production"


def hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return PASSWORDS.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORDS.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_session(db: Session, user: User) -> tuple[str, str, SessionRecord]:
    raw_session = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    record = SessionRecord(
        user_id=user.id,
        token_hash=hash_token(raw_session),
        csrf_hash=hash_token(raw_csrf),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=SESSION_HOURS),
    )
    db.add(record)
    db.flush()
    return raw_session, raw_csrf, record


def get_session(db: Session, request: Request) -> tuple[SessionRecord, User]:
    raw_token = request.cookies.get(SESSION_COOKIE)
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in is required.")
    record = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == hash_token(raw_token)))
    now = datetime.now(timezone.utc)
    if record is None or record.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid.")
    expires = record.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has expired.")
    user = db.get(User, record.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session is invalid.")
    return record, user


def require_csrf(request: Request, record: SessionRecord | None = None) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token is missing or invalid.")
    if record is not None and not hmac.compare_digest(hash_token(cookie_token), record.csrf_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token is invalid.")


def set_session_cookies(response, raw_session: str, raw_csrf: str) -> None:
    common = {"secure": COOKIE_SECURE, "samesite": "lax"}
    response.set_cookie(
        SESSION_COOKIE, raw_session, max_age=SESSION_HOURS * 3600,
        httponly=True, path="/", **common,
    )
    response.set_cookie(
        CSRF_COOKIE, raw_csrf, max_age=SESSION_HOURS * 3600,
        httponly=False, path="/api/v1", **common,
    )


def clear_session_cookies(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/api/v1")
