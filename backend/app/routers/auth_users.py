from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import log
from ..auth import current_user, hash_password, issue_token, require_role, revoke_token, verify_password
from ..db import get_db
from ..models import ROLES, User
from ..serializers import user_out

router = APIRouter(prefix="/api", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class SetupIn(BaseModel):
    username: str = Field(min_length=2)
    display_name: str = ""
    password: str = Field(min_length=8)


class UserIn(BaseModel):
    username: str = Field(min_length=2)
    display_name: str = ""
    role: str = "librarian"
    password: str = Field(min_length=8)


class UserPatch(BaseModel):
    display_name: str | None = None
    role: str | None = None
    active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


@router.get("/setup/status")
def setup_status(db: Session = Depends(get_db)):
    return {"needs_setup": db.scalar(select(func.count(User.id))) == 0}


@router.post("/setup")
def setup(data: SetupIn, db: Session = Depends(get_db)):
    """Create the first admin. Only possible while there are no users."""
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "המערכת כבר הוגדרה")
    u = User(username=data.username, display_name=data.display_name or data.username, role="admin",
             password_hash=hash_password(data.password))
    db.add(u)
    db.flush()
    log(db, data.username, "user", "setup_admin", u.id)
    db.commit()
    return {"token": issue_token(db, u), "user": user_out(u)}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.username == data.username))
    if not u or not u.active or not verify_password(data.password, u.password_hash):
        raise HTTPException(401, "שם משתמש או סיסמה שגויים")
    log(db, u.username, "user", "login", u.id)
    db.commit()
    return {"token": issue_token(db, u), "user": user_out(u)}


@router.post("/logout")
def logout(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    revoke_token(db, authorization.removeprefix("Bearer ").strip())
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    return [user_out(u) for u in db.scalars(select(User).order_by(User.username))]


@router.post("/users")
def create_user(data: UserIn, db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    if data.role not in ROLES:
        raise HTTPException(400, "תפקיד לא חוקי")
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(409, "שם המשתמש קיים")
    u = User(username=data.username, display_name=data.display_name or data.username, role=data.role,
             password_hash=hash_password(data.password))
    db.add(u)
    db.flush()
    log(db, admin.username, "user", "create", u.id, role=data.role, username=data.username)
    db.commit()
    return user_out(u)


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserPatch, db: Session = Depends(get_db), admin: User = Depends(require_role("admin"))):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "משתמש לא נמצא")
    changes = {}
    if data.display_name is not None:
        u.display_name = changes["display_name"] = data.display_name
    if data.role is not None:
        if data.role not in ROLES:
            raise HTTPException(400, "תפקיד לא חוקי")
        u.role = changes["role"] = data.role
    if data.active is not None:
        u.active = changes["active"] = data.active
    if data.password:
        u.password_hash = hash_password(data.password)
        changes["credentials_changed"] = True
    log(db, admin.username, "user", "update", u.id, **changes)
    db.commit()
    return user_out(u)
