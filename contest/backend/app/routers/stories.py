"""Собственный рассказ участника. Редактирование возможно только в фазе приёма работ."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_contest, require_participant, require_phase
from ..models import Contest, Story, User
from ..schemas import StoryIn
from ..services_time import iso, utcnow

router = APIRouter(prefix="/api/stories", tags=["stories"])


def _own(db: Session, contest: Contest, user: User) -> Story | None:
    return db.scalar(select(Story).where(Story.contest_id == contest.id, Story.author_id == user.id))


def _out(s: Story) -> dict:
    return {
        "title": s.title,
        "body": s.body,
        "disclaimer": s.disclaimer,
        "created_at": iso(s.created_at),
        "updated_at": iso(s.updated_at),
    }


@router.get("/me")
def get_my_story(
    user: User = Depends(require_participant),
    contest: Contest = Depends(get_contest),
    db: Session = Depends(get_db),
):
    story = _own(db, contest, user)
    return _out(story) if story else None


@router.put("/me")
def put_my_story(
    data: StoryIn,
    user: User = Depends(require_participant),
    contest: Contest = Depends(require_phase("submission")),
    db: Session = Depends(get_db),
):
    story = _own(db, contest, user)
    if story is None:
        story = Story(
            contest_id=contest.id,
            author_id=user.id,
            title=data.title,
            body=data.body,
            disclaimer=data.disclaimer,
        )
        db.add(story)
    else:
        story.title, story.body, story.disclaimer, story.updated_at = data.title, data.body, data.disclaimer, utcnow()
    db.commit()
    return _out(story)


@router.delete("/me", status_code=204)
def delete_my_story(
    user: User = Depends(require_participant),
    contest: Contest = Depends(require_phase("submission")),
    db: Session = Depends(get_db),
):
    story = _own(db, contest, user)
    if not story:
        raise HTTPException(404, "Рассказ не найден")
    db.delete(story)
    db.commit()
    return Response(status_code=204)
