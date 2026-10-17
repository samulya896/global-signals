"""Email/password registration and revocable, HttpOnly server-side sessions."""

from datetime import datetime, timezone
from decimal import Decimal
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import get_db
from .config import SETTINGS
from .models import AuditEvent, PortfolioSnapshot, SessionRecord, User, VirtualPortfolio
from .rate_limit import enforce_rate_limit
from .schemas import Credentials, PasswordConfirmation
from .security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    clear_session_cookies,
    create_session,
    get_session,
    hash_password,
    hash_token,
    require_csrf,
    set_session_cookies,
    verify_password,
)


router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
STARTING_CASH = SETTINGS.starting_cash
_DUMMY_HASH = hash_password(secrets.token_urlsafe(40))


def public_user(user: User) -> dict:
    return {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}


@router.get("/csrf")
def csrf_token(request: Request, response: Response, db: Session = Depends(get_db)):
    raw_csrf = request.cookies.get(CSRF_COOKIE)
    raw_session = request.cookies.get(SESSION_COOKIE)
    if raw_session:
        record = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == hash_token(raw_session)))
        if record and record.revoked_at is None:
            expires = record.expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires > datetime.now(timezone.utc):
                if raw_csrf and record.csrf_hash == hash_token(raw_csrf):
                    return {"csrf_token": raw_csrf}
                raw_csrf = secrets.token_urlsafe(32)
                record.csrf_hash = hash_token(raw_csrf)
                db.commit()
    if not raw_csrf:
        raw_csrf = secrets.token_urlsafe(32)
    secure = os.getenv("APP_ENV", "development").lower() == "production"
    response.set_cookie(CSRF_COOKIE, raw_csrf, httponly=False, secure=secure, samesite="lax", path="/api/v1", max_age=3600)
    return {"csrf_token": raw_csrf}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(payload: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "register", 5, 3600)
    require_csrf(request)
    email = str(payload.email).strip().casefold()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Unable to register with those details.")

    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    portfolio = VirtualPortfolio(user_id=user.id, starting_cash=STARTING_CASH, cash=STARTING_CASH)
    db.add(portfolio)
    db.flush()
    db.add(PortfolioSnapshot(
        portfolio_id=portfolio.id,
        cash=STARTING_CASH,
        market_value=Decimal("0"),
        equity=STARTING_CASH,
    ))
    db.add(AuditEvent(user_id=user.id, event_type="account_registered"))
    raw_session, raw_csrf, _record = create_session(db, user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Unable to register with those details.") from exc
    set_session_cookies(response, raw_session, raw_csrf)
    return {"user": public_user(user), "csrf_token": raw_csrf}


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "login", 10, 900)
    require_csrf(request)
    email = str(payload.email).strip().casefold()
    user = db.scalar(select(User).where(User.email == email))
    correct = verify_password(user.password_hash if user else _DUMMY_HASH, payload.password)
    if user is None or not correct:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    raw_session, raw_csrf, _record = create_session(db, user)
    db.add(AuditEvent(user_id=user.id, event_type="session_created"))
    db.commit()
    set_session_cookies(response, raw_session, raw_csrf)
    return {"user": public_user(user), "csrf_token": raw_csrf}


@router.get("/me")
def me(request: Request, db: Session = Depends(get_db)):
    _session, user = get_session(db, request)
    return {"user": public_user(user)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    record, user = get_session(db, request)
    require_csrf(request, record)
    record.revoked_at = datetime.now(timezone.utc)
    db.add(AuditEvent(user_id=user.id, event_type="session_revoked", object_id=record.id))
    db.commit()
    clear_session_cookies(response)
    return {"status": "signed_out"}


@router.post("/password-reset")
def password_reset_unavailable(request: Request):
    # Never claim a reset message was sent when no email provider is configured.
    enforce_rate_limit(request, "password_reset", 5, 3600)
    if not os.getenv("EMAIL_PROVIDER_URL") or not os.getenv("EMAIL_PROVIDER_API_KEY"):
        raise HTTPException(status_code=503, detail="Password reset email is not configured; no email was sent.")
    raise HTTPException(status_code=501, detail="Configured password reset delivery is not implemented yet.")


@router.delete("/me")
def delete_account(payload: PasswordConfirmation, request: Request, response: Response, db: Session = Depends(get_db)):
    record, user = get_session(db, request)
    require_csrf(request, record)
    if not verify_password(user.password_hash, payload.password):
        raise HTTPException(status_code=401, detail="Password confirmation failed.")
    db.add(AuditEvent(user_id=None, event_type="account_deleted", object_id=None))
    db.delete(user)
    db.commit()
    clear_session_cookies(response)
    return {"status": "account_deleted"}
