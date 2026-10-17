"""Кабинет организатора. Авторов рассказов он не видит до финала, как и все."""
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import require_organizer
from ..models import Contest, Invite, Rating, Review, Star, Story, User
from ..schemas import ContestCreateIn, ContestPatchIn, InvitesIn
from ..services import advance, contest_to_dict, current_contest
from ..services_time import iso, utcnow

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_organizer)])


def _check_deadlines(phase: str, sub, vote) -> None:
    now = utcnow()
    if sub and sub <= now and phase in ("draft", "submission"):
        raise HTTPException(422, "Дедлайн приёма работ должен быть в будущем")
    if vote and vote <= now:
        raise HTTPException(422, "Дедлайн оценивания должен быть в будущем")
    if sub and vote and vote <= sub:
        raise HTTPException(422, "Оценивание должно заканчиваться позже приёма работ")


@router.post("/contest")
def create_contest(
    data: ContestCreateIn, user: User = Depends(require_organizer), db: Session = Depends(get_db)
):
    last = current_contest(db)
    if last and last.phase != "results":
        raise HTTPException(409, "Предыдущий конкурс ещё не завершён")
    _check_deadlines("draft", data.submission_ends_at, data.voting_ends_at)
    contest = Contest(
        theme=data.theme.strip(),
        submission_ends_at=data.submission_ends_at,
        voting_ends_at=data.voting_ends_at,
        voters_must_submit=data.voters_must_submit,
    )
    db.add(contest)
    db.commit()
    return contest_to_dict(db, contest, user)


@router.patch("/contest")
def patch_contest(
    data: ContestPatchIn, user: User = Depends(require_organizer), db: Session = Depends(get_db)
):
    contest = current_contest(db)
    if not contest:
        raise HTTPException(404, "Конкурс ещё не создан")
    sent = data.model_fields_set
    phase = contest.phase

    if "theme" in sent and data.theme is not None:
        if phase != "draft":
            raise HTTPException(409, "Тему можно менять только до старта конкурса")
        contest.theme = data.theme.strip()
    if "voters_must_submit" in sent and data.voters_must_submit is not None:
        if phase in ("voting", "results"):
            raise HTTPException(409, "Правило голосования нельзя менять после начала оценивания")
        contest.voters_must_submit = data.voters_must_submit

    sub = data.submission_ends_at if "submission_ends_at" in sent else contest.submission_ends_at
    vote = data.voting_ends_at if "voting_ends_at" in sent else contest.voting_ends_at
    if "submission_ends_at" in sent:
        if phase not in ("draft", "submission"):
            raise HTTPException(409, "Приём работ уже закрыт")
        _check_deadlines(phase, data.submission_ends_at, None)
    if "voting_ends_at" in sent:
        if phase == "results":
            raise HTTPException(409, "Оценивание уже закрыто")
        _check_deadlines(phase, None, data.voting_ends_at)
    _check_deadlines(phase, None, None)
    if sub and vote and vote <= sub:
        raise HTTPException(422, "Оценивание должно заканчиваться позже приёма работ")
    contest.submission_ends_at, contest.voting_ends_at = sub, vote
    db.commit()
    return contest_to_dict(db, contest, user)


@router.post("/contest/advance")
def advance_contest(user: User = Depends(require_organizer), db: Session = Depends(get_db)):
    """Следующая фаза: draft → submission → voting → results (назад пути нет)."""
    contest = current_contest(db)
    if not contest:
        raise HTTPException(404, "Конкурс ещё не создан")
    try:
        advance(db, contest)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return contest_to_dict(db, contest, user)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    contest = current_contest(db)
    participants = db.scalar(select(func.count(User.id)).where(User.role == "participant"))
    invites_total = db.scalar(select(func.count(Invite.token)))
    invites_used = db.scalar(select(func.count(Invite.token)).where(Invite.used_by.is_not(None)))
    out = {
        "participants": participants,
        "invites_total": invites_total,
        "invites_used": invites_used,
        "stories": 0,
        "ratings": 0,
        "reviews": 0,
        "stars": 0,
    }
    if contest:
        out["stories"] = db.scalar(select(func.count(Story.id)).where(Story.contest_id == contest.id))
        out["ratings"] = db.scalar(
            select(func.count(Rating.id)).join(Story, Story.id == Rating.story_id).where(Story.contest_id == contest.id)
        )
        out["reviews"] = db.scalar(
            select(func.count(Review.id)).join(Story, Story.id == Review.story_id).where(Story.contest_id == contest.id)
        )
        out["stars"] = db.scalar(select(func.count(Star.id)).where(Star.contest_id == contest.id))
    return out


def _invite_out(i: Invite) -> dict:
    return {
        "token": i.token,
        "created_at": iso(i.created_at),
        "expires_at": iso(i.expires_at),
        "used": i.used_by is not None,
        "used_by": i.user.nickname if i.user else None,
    }


@router.get("/invites")
def list_invites(db: Session = Depends(get_db)):
    invites = db.scalars(
        select(Invite).options(selectinload(Invite.user)).order_by(Invite.created_at.desc())
    ).all()
    return [_invite_out(i) for i in invites]


@router.post("/invites")
def create_invites(data: InvitesIn, db: Session = Depends(get_db)):
    expires = utcnow() + timedelta(days=data.expires_in_days) if data.expires_in_days else None
    invites = [Invite(token=str(uuid.uuid4()), expires_at=expires) for _ in range(data.count)]
    db.add_all(invites)
    db.commit()
    return [_invite_out(i) for i in invites]


@router.delete("/invites/{token}", status_code=204)
def delete_invite(token: str, db: Session = Depends(get_db)):
    invite = db.get(Invite, token)
    if not invite:
        raise HTTPException(404, "Приглашение не найдено")
    if invite.used_by is not None:
        raise HTTPException(409, "Приглашение уже использовано")
    db.delete(invite)
    db.commit()
