"""Итоги. Единственное место, где раскрываются авторы."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import get_current_user, require_phase
from ..models import Contest, Review, Story, User
from ..services import compute_results, story_result

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get("")
def results(
    _: User = Depends(get_current_user),
    contest: Contest = Depends(require_phase("results")),
    db: Session = Depends(get_db),
):
    return compute_results(db, contest)


@router.get("/stories")
def all_stories(
    _: User = Depends(get_current_user),
    contest: Contest = Depends(require_phase("results")),
    db: Session = Depends(get_db),
):
    """Все работы финала (в т.ч. не попавшие в топы), чтобы любую можно было прочитать с рецензиями."""
    counts = dict(
        db.execute(
            select(Review.story_id, func.count(Review.id))
            .join(Story, Story.id == Review.story_id)
            .where(Story.contest_id == contest.id)
            .group_by(Review.story_id)
        ).all()
    )
    stories = db.scalars(
        select(Story)
        .where(Story.contest_id == contest.id, Story.anon_number.is_not(None))
        .options(selectinload(Story.author))
        .order_by(Story.anon_number)
    ).all()
    return [
        {
            "anon_number": s.anon_number,
            "title": s.title,
            "author": s.author.nickname,
            "words": len(s.body.split()),
            "reviews": counts.get(s.id, 0),
        }
        for s in stories
    ]


@router.get("/stories/{anon_number}")
def result_story(
    anon_number: int,
    _: User = Depends(get_current_user),
    contest: Contest = Depends(require_phase("results")),
    db: Session = Depends(get_db),
):
    story = db.scalar(
        select(Story)
        .where(Story.contest_id == contest.id, Story.anon_number == anon_number)
        .options(selectinload(Story.author))
    )
    if not story:
        raise HTTPException(404, "Рассказ не найден")
    return story_result(db, contest, story)
