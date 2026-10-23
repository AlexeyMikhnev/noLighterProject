"""Анонимное оценивание. Здесь НИГДЕ нет автора: ни id, ни псевдонима, ни времени загрузки."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import SCALE_KEYS, STARS_PER_USER
from ..db import get_db
from ..deps import require_participant, require_phase
from ..models import Contest, Rating, Review, Star, Story, Survey, User
from ..richtext import word_count
from ..schemas import RatingIn, ReviewIn, SurveyIn
from ..services import survey_dict
from ..services_time import utcnow

router = APIRouter(prefix="/api/voting", tags=["voting"])


def voter(
    user: User = Depends(require_participant),
    contest: Contest = Depends(require_phase("voting")),
    db: Session = Depends(get_db),
) -> tuple[User, Contest]:
    if contest.voters_must_submit:
        has_story = db.scalar(
            select(Story.id).where(Story.contest_id == contest.id, Story.author_id == user.id)
        )
        if has_story is None:
            raise HTTPException(403, "Оценивать могут только участники, приславшие свой рассказ")
    return user, contest


def _story(db: Session, contest: Contest, user: User, anon_number: int) -> Story:
    story = db.scalar(
        select(Story).where(Story.contest_id == contest.id, Story.anon_number == anon_number)
    )
    if not story:
        raise HTTPException(404, "Рассказ не найден")
    if story.author_id == user.id:
        raise HTTPException(403, "Нельзя оценивать собственный рассказ")
    return story


def _stars_left(db: Session, contest: Contest, user: User) -> int:
    used = db.scalar(
        select(func.count(Star.id)).where(Star.contest_id == contest.id, Star.giver_id == user.id)
    )
    return STARS_PER_USER - used


def _rating_dict(r: Rating | None) -> dict | None:
    return {k: getattr(r, k) for k in SCALE_KEYS} if r else None


def _item(s: Story, rating: Rating | None, starred: bool, reviewed: bool = False) -> dict:
    return {
        "anon_number": s.anon_number,
        "title": s.title,
        "words": word_count(s.body),
        "rated": rating is not None,
        "starred": starred,
        "reviewed": reviewed,
    }


def _my_survey(db: Session, story: Story, user: User) -> Survey | None:
    return db.scalar(select(Survey).where(Survey.story_id == story.id, Survey.rater_id == user.id))


def _my_review(db: Session, story: Story, user: User) -> Review | None:
    return db.scalar(select(Review).where(Review.story_id == story.id, Review.reviewer_id == user.id))


@router.get("/stories")
def list_stories(ctx=Depends(voter), db: Session = Depends(get_db)):
    user, contest = ctx
    stories = db.scalars(
        select(Story)
        .where(Story.contest_id == contest.id, Story.author_id != user.id)
        .order_by(Story.anon_number)
    ).all()
    ratings = {
        r.story_id: r for r in db.scalars(select(Rating).where(Rating.rater_id == user.id)).all()
    }
    starred = set(
        db.scalars(
            select(Star.story_id).where(Star.contest_id == contest.id, Star.giver_id == user.id)
        ).all()
    )
    reviewed = set(db.scalars(select(Review.story_id).where(Review.reviewer_id == user.id)).all())
    return {
        "stories": [_item(s, ratings.get(s.id), s.id in starred, s.id in reviewed) for s in stories],
        "stars_total": STARS_PER_USER,
        "stars_left": _stars_left(db, contest, user),
    }


@router.get("/stories/{anon_number}")
def read_story(anon_number: int, ctx=Depends(voter), db: Session = Depends(get_db)):
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    rating = db.scalar(select(Rating).where(Rating.story_id == s.id, Rating.rater_id == user.id))
    starred = db.scalar(select(Star.id).where(Star.story_id == s.id, Star.giver_id == user.id))
    return {
        "anon_number": s.anon_number,
        "title": s.title,
        "body": s.body,
        "disclaimer": s.disclaimer,
        "my_rating": _rating_dict(rating),
        "starred": starred is not None,
        "my_review": review.body if (review := _my_review(db, s, user)) else None,
        "my_survey": survey_dict(_my_survey(db, s, user)),
    }


@router.put("/stories/{anon_number}/rating")
def put_rating(anon_number: int, data: RatingIn, ctx=Depends(voter), db: Session = Depends(get_db)):
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    rating = db.scalar(select(Rating).where(Rating.story_id == s.id, Rating.rater_id == user.id))
    if rating is None:
        rating = Rating(story_id=s.id, rater_id=user.id, **data.model_dump())
        db.add(rating)
    else:
        for k, v in data.model_dump().items():
            setattr(rating, k, v)
    db.commit()
    starred = db.scalar(select(Star.id).where(Star.story_id == s.id, Star.giver_id == user.id))
    return _item(s, rating, starred is not None, _my_review(db, s, user) is not None)


@router.put("/stories/{anon_number}/survey")
def put_survey(anon_number: int, data: SurveyIn, ctx=Depends(voter), db: Session = Depends(get_db)):
    """Опросник для статистики: не влияет на оценки и топы. Пустые ответы = опросник удалён."""
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    survey = _my_survey(db, s, user)
    if data.is_empty():
        if survey:
            db.delete(survey)
            db.commit()
        return {"my_survey": None}
    if survey is None:
        survey = Survey(story_id=s.id, rater_id=user.id)
        db.add(survey)
    for k, v in data.model_dump().items():
        setattr(survey, k, v)
    db.commit()
    return {"my_survey": survey_dict(survey)}


@router.put("/stories/{anon_number}/star")
def give_star(anon_number: int, ctx=Depends(voter), db: Session = Depends(get_db)):
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    exists = db.scalar(select(Star.id).where(Star.story_id == s.id, Star.giver_id == user.id))
    if exists is None:
        if _stars_left(db, contest, user) <= 0:
            raise HTTPException(409, f"Все звёзды ({STARS_PER_USER}) уже розданы")
        db.add(Star(contest_id=contest.id, story_id=s.id, giver_id=user.id))
        db.commit()
    return {"starred": True, "stars_left": _stars_left(db, contest, user)}


@router.delete("/stories/{anon_number}/star")
def take_star_back(anon_number: int, ctx=Depends(voter), db: Session = Depends(get_db)):
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    star = db.scalar(select(Star).where(Star.story_id == s.id, Star.giver_id == user.id))
    if star:
        db.delete(star)
        db.commit()
    return {"starred": False, "stars_left": _stars_left(db, contest, user)}


@router.put("/stories/{anon_number}/review")
def put_review(anon_number: int, data: ReviewIn, ctx=Depends(voter), db: Session = Depends(get_db)):
    """Анонимная рецензия: одна на рассказ, можно переписать, пока идёт оценивание."""
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    review = _my_review(db, s, user)
    if review is None:
        db.add(Review(story_id=s.id, reviewer_id=user.id, body=data.body))
    else:
        review.body, review.updated_at = data.body, utcnow()
    db.commit()
    return {"my_review": data.body}


@router.delete("/stories/{anon_number}/review")
def delete_review(anon_number: int, ctx=Depends(voter), db: Session = Depends(get_db)):
    user, contest = ctx
    s = _story(db, contest, user, anon_number)
    review = _my_review(db, s, user)
    if review:
        db.delete(review)
        db.commit()
    return {"my_review": None}
