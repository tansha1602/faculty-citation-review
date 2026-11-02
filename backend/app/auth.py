"""Local users with roles: admin, librarian, reviewer.

Passwords are stored as PBKDF2-SHA256 hashes; session tokens are stored hashed.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import SessionToken, User

ITERATIONS = 390_000
TOKEN_HOURS = 12


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, it, salt, digest = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except Exception:
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(SessionToken(token_hash=_hash_token(token), user_id=user.id,
                        expires_at=datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)))
    db.commit()
    return token


def revoke_token(db: Session, token: str) -> None:
    t = db.scalar(select(SessionToken).where(SessionToken.token_hash == _hash_token(token)))
    if t:
        db.delete(t)
        db.commit()


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(401, "נדרשת התחברות")
    t = db.scalar(select(SessionToken).where(SessionToken.token_hash == _hash_token(token)))
    if not t:
        raise HTTPException(401, "החיבור פג תוקף — יש להתחבר מחדש")
    exp = t.expires_at if t.expires_at.tzinfo else t.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc) or not t.user.active:
        raise HTTPException(401, "החיבור פג תוקף — יש להתחבר מחדש")
    return t.user


def require_role(*roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "אין לך הרשאה לפעולה זו")
        return user
    return dep


def ensure_initial_admin(db: Session) -> str | None:
    """Create the first admin from FCR_ADMIN_USER / FCR_ADMIN_PASSWORD if no users exist."""
    if db.scalar(select(User).limit(1)):
        return None
    username = os.environ.get("FCR_ADMIN_USER", "admin")
    password = os.environ.get("FCR_ADMIN_PASSWORD")
    if not password:
        return None
    db.add(User(username=username, display_name="מנהל מערכת", role="admin", password_hash=hash_password(password)))
    db.commit()
    return username
