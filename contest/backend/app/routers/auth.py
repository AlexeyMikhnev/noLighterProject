from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import Invite, User
from ..schemas import LoginIn, RegisterIn
from ..security import create_token, hash_password, verify_password
from ..services_time import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "nickname": u.nickname, "role": u.role}


def _token_out(u: User) -> dict:
    return {"access_token": create_token(u.id), "user": _user_out(u)}


def _invite_is_valid(inv: Invite | None) -> bool:
    return bool(inv and inv.used_by is None and (inv.expires_at is None or inv.expires_at > utcnow()))


@router.get("/invite/{token}")
def check_invite(token: str, db: Session = Depends(get_db)):
    return {"valid": _invite_is_valid(db.get(Invite, token))}


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    invite = db.get(Invite, data.invite_token)
    if not _invite_is_valid(invite):
        raise HTTPException(400, "Ссылка-приглашение недействительна или уже использована")
    if db.scalar(select(User.id).where(User.email == data.email)):
        raise HTTPException(409, "Этот email уже зарегистрирован")
    if db.scalar(select(User.id).where(func.lower(User.nickname) == data.nickname.lower())):
        raise HTTPException(409, "Этот псевдоним уже занят")
    user = User(
        email=data.email,
        nickname=data.nickname,
        password_hash=hash_password(data.password),
        role="participant",
    )
    db.add(user)
    try:
        db.flush()
        invite.used_by = user.id
        invite.used_at = utcnow()
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email или псевдоним уже заняты")
    return _token_out(user)


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Неверный email или пароль")
    return _token_out(user)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return _user_out(user)
