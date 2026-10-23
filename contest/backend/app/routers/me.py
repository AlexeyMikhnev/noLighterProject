"""Личный кабинет участника: архив участий, свои оценки и рецензии.

Правила те же, что и везде:
- чужие рассказы здесь только под анонимными номерами; псевдонимы авторов добавляются
  лишь для конкурсов в фазе «results»;
- то, что получил ваш рассказ (оценки, звёзды, рецензии), скрыто до финала;
- авторы рецензий не раскрываются никогда.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import SCALE_KEYS, SCALES
from ..db import get_db
from ..deps import require_participant
from ..models import Contest, Rating, Review, Star, Story, User
from ..services import compute_results, story_result
from ..services_time import iso

router = APIRouter(prefix="/api/me", tags=["me"])


def _own_story(db: Session, contest: Contest, user: User) -> Story | None:
    return db.scalar(select(Story).where(Story.contest_id == contest.id, Story.author_id == user.id))


def _given(db: Session, contest: Contest, user: User) -> list[dict]:
    """Всё, что пользователь отдал чужим рассказам: оценка, звезда, рецензия."""
    ratings = {
        r.story_id: r
        for r in db.scalars(
            select(Rating).join(Story, Story.id == Rating.story_id).where(
                Story.contest_id == contest.id, Rating.rater_id == user.id
            )
        )
    }
    reviews = {
        r.story_id: r
        for r in db.scalars(
            select(Review).join(Story, Story.id == Review.story_id).where(
                Story.contest_id == contest.id, Review.reviewer_id == user.id
            )
        )
    }
    starred = set(
        db.scalars(select(Star.story_id).where(Star.contest_id == contest.id, Star.giver_id == user.id))
    )
    ids = set(ratings) | set(reviews) | starred
    if not ids:
        return []
    stories = db.scalars(
        select(Story).where(Story.id.in_(ids)).options(selectinload(Story.author)).order_by(Story.anon_number)
    ).all()
    reveal = contest.phase == "results"
    out = []
    for s in stories:
        r = ratings.get(s.id)
        out.append(
            {
                "anon_number": s.anon_number,
                "title": s.title,
                "author": s.author.nickname if reveal else None,
                "rating": {k: getattr(r, k) for k in SCALE_KEYS} if r else None,
                "starred": s.id in starred,
                "review": reviews[s.id].body if s.id in reviews else None,
            }
        )
    return out


def _participated(db: Session, contest: Contest, user: User) -> bool:
    return (
        _own_story(db, contest, user) is not None
        or db.scalar(
            select(Rating.id)
            .join(Story, Story.id == Rating.story_id)
            .where(Story.contest_id == contest.id, Rating.rater_id == user.id)
            .limit(1)
        )
        is not None
        or db.scalar(select(Star.id).where(Star.contest_id == contest.id, Star.giver_id == user.id).limit(1))
        is not None
        or db.scalar(
            select(Review.id)
            .join(Story, Story.id == Review.story_id)
            .where(Story.contest_id == contest.id, Review.reviewer_id == user.id)
            .limit(1)
        )
        is not None
    )


@router.get("/contests")
def my_contests(user: User = Depends(require_participant), db: Session = Depends(get_db)):
    """Архив: все конкурсы, в которых пользователь участвовал, от новых к старым."""
    contests = db.scalars(select(Contest).order_by(Contest.id.desc())).all()
    out = []
    for c in contests:
        if not _participated(db, c, user):
            continue
        story = _own_story(db, c, user)
        given = _given(db, c, user)
        out.append(
            {
                "id": c.id,
                "theme": c.theme if c.phase != "draft" else None,
                "phase": c.phase,
                "created_at": iso(c.created_at),
                "story_title": story.title if story else None,
                "given": {
                    "ratings": sum(1 for g in given if g["rating"]),
                    "stars": sum(1 for g in given if g["starred"]),
                    "reviews": sum(1 for g in given if g["review"]),
                },
            }
        )
    return out


def _received(db: Session, contest: Contest, story: Story) -> dict:
    """Итоги своего рассказа: средние по шкалам с местами, звёзды, рецензии."""
    res = compute_results(db, contest)
    mine = story_result(db, contest, story)
    scales = []
    for key, label, _ in SCALES:
        entry = next((e for e in next(s for s in res["scales"] if s["key"] == key)["ranking"]
                      if e["anon_number"] == story.anon_number), None)
        scales.append(
            {
                "key": key,
                "label": label,
                "value": entry["value"] if entry else None,
                "rank": entry["rank"] if entry else None,
            }
        )
    star_entry = next((e for e in res["stars"]["ranking"] if e["anon_number"] == story.anon_number), None)
    return {
        "votes": mine["votes"],
        "scales": scales,
        "stars": mine["stars"],
        "stars_rank": star_entry["rank"] if star_entry else None,
        "reviews": mine["reviews"],
    }


@router.get("/contests/{contest_id}")
def my_contest(contest_id: int, user: User = Depends(require_participant), db: Session = Depends(get_db)):
    contest = db.get(Contest, contest_id)
    if not contest or not _participated(db, contest, user):
        raise HTTPException(404, "Вы не участвовали в этом конкурсе")
    story = _own_story(db, contest, user)
    results_open = contest.phase == "results"
    return {
        "contest": {
            "id": contest.id,
            "theme": contest.theme if contest.phase != "draft" else None,
            "phase": contest.phase,
        },
        "story": (
            {
                "title": story.title,
                "body": story.body,
                "disclaimer": story.disclaimer,
                "anon_number": story.anon_number if results_open else None,
                "created_at": iso(story.created_at),
                "updated_at": iso(story.updated_at),
            }
            if story
            else None
        ),
        # Полученное скрыто до финала.
        "received": _received(db, contest, story) if (story and results_open) else None,
        "received_hidden": bool(story) and not results_open,
        "given": _given(db, contest, user),
    }
