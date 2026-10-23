"""Бизнес-логика: фазы конкурса, подсчёт топов."""
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import SCALE_KEYS, SCALES, STARS_PER_USER, SURVEY, SURVEY_BOOL_KEYS
from .models import Contest, Rating, Review, Star, Story, Survey, User
from .services_time import iso, utcnow

PHASES = ["draft", "submission", "voting", "results"]


# ---------- фазы ----------


def current_contest(db: Session) -> Contest | None:
    contest = db.scalar(select(Contest).order_by(Contest.id.desc()).limit(1))
    if contest:
        sync_phase(db, contest)
    return contest


def sync_phase(db: Session, contest: Contest) -> None:
    """Ленивая смена фазы по дедлайнам: выполняется при каждом обращении к конкурсу."""
    while True:
        now = utcnow()
        if contest.phase == "submission" and contest.submission_ends_at and now >= contest.submission_ends_at:
            advance(db, contest)
        elif contest.phase == "voting" and contest.voting_ends_at and now >= contest.voting_ends_at:
            advance(db, contest)
        else:
            return


def advance(db: Session, contest: Contest) -> None:
    idx = PHASES.index(contest.phase)
    if idx == len(PHASES) - 1:
        raise ValueError("Конкурс уже завершён")
    nxt = PHASES[idx + 1]
    if nxt == "voting":
        assign_anon_numbers(db, contest)
    contest.phase = nxt
    db.commit()


def assign_anon_numbers(db: Session, contest: Contest) -> None:
    """Случайные номера 1..N: порядок не выдаёт, кто и когда прислал рассказ."""
    stories = db.scalars(select(Story).where(Story.contest_id == contest.id)).all()
    if any(s.anon_number is not None for s in stories):
        return
    numbers = list(range(1, len(stories) + 1))
    random.SystemRandom().shuffle(numbers)
    for story, n in zip(stories, numbers):
        story.anon_number = n
    db.flush()


# ---------- представление конкурса ----------


def _survey_question(q: dict) -> dict:
    out = {"key": q["key"], "label": q["label"], "type": q["type"]}
    if "options" in q:
        out["options"] = [{"key": k, "label": label} for k, label in q["options"]]
    return out


def survey_dict(sv: Survey | None) -> dict | None:
    """Ответы одного читателя (видит только он сам)."""
    if sv is None:
        return None
    return {
        "genres": list(sv.genres or []),
        "settings": list(sv.settings or []),
        "hero_gender": sv.hero_gender,
        **{k: getattr(sv, k) for k in SURVEY_BOOL_KEYS},
    }


def survey_stats(rows: list[Survey]) -> dict:
    """Агрегаты опросника: сколько читателей выбрали каждый вариант. Без привязки к читателям."""
    questions = []
    for q in SURVEY:
        key = q["key"]
        if q["type"] == "bool":
            vals = [getattr(r, key) for r in rows if getattr(r, key) is not None]
            counts = {"yes": sum(1 for v in vals if v), "no": sum(1 for v in vals if not v)}
            options = [{"key": "yes", "label": "Да", "count": counts["yes"]}, {"key": "no", "label": "Нет", "count": counts["no"]}]
            answered = len(vals)
        elif q["type"] == "single":
            vals = [getattr(r, key) for r in rows if getattr(r, key)]
            options = [{"key": k, "label": label, "count": vals.count(k)} for k, label in q["options"]]
            answered = len(vals)
        else:
            vals = [getattr(r, key) or [] for r in rows]
            options = [{"key": k, "label": label, "count": sum(1 for v in vals if k in v)} for k, label in q["options"]]
            answered = sum(1 for v in vals if v)
        questions.append({"key": key, "label": q["label"], "type": q["type"], "answered": answered, "options": options})
    return {"respondents": len(rows), "questions": questions}


def contest_to_dict(db: Session, contest: Contest, user: User) -> dict:
    is_org = user.role == "organizer"
    data = {
        "id": contest.id,
        "phase": contest.phase,
        "phases": PHASES,
        # До старта тему видит только организатор.
        "theme": contest.theme if (is_org or contest.phase != "draft") else None,
        "submission_ends_at": iso(contest.submission_ends_at),
        "voting_ends_at": iso(contest.voting_ends_at),
        "voters_must_submit": contest.voters_must_submit,
        "scales": [{"key": k, "label": label, "hint": hint} for k, label, hint in SCALES],
        "stars_total": STARS_PER_USER,
        "survey": [_survey_question(q) for q in SURVEY],
        "me": None,
    }
    if not is_org:
        has_story = db.scalar(
            select(Story.id).where(Story.contest_id == contest.id, Story.author_id == user.id)
        ) is not None
        me = {"has_story": has_story, "can_vote": has_story or not contest.voters_must_submit}
        if contest.phase in ("voting", "results"):
            me["stars_used"] = db.scalar(
                select(func.count(Star.id)).where(Star.contest_id == contest.id, Star.giver_id == user.id)
            )
            me["rated_count"] = db.scalar(
                select(func.count(Rating.id))
                .join(Story, Story.id == Rating.story_id)
                .where(Story.contest_id == contest.id, Rating.rater_id == user.id)
            )
            me["reviews_written"] = db.scalar(
                select(func.count(Review.id))
                .join(Story, Story.id == Review.story_id)
                .where(Story.contest_id == contest.id, Review.reviewer_id == user.id)
            )
            me["to_rate"] = db.scalar(
                select(func.count(Story.id)).where(Story.contest_id == contest.id, Story.author_id != user.id)
            )
        data["me"] = me
    return data


# ---------- результаты ----------


def _ranked(entries: list[dict], tiebreak_by_votes: bool) -> list[dict]:
    """Места как в спорте: при равенстве значения место общее (1, 2, 2, 4)."""
    if tiebreak_by_votes:
        ordered = sorted(entries, key=lambda e: (-e["value"], -e["votes"], e["anon_number"]))
    else:
        ordered = sorted(entries, key=lambda e: (-e["value"], e["anon_number"]))
    out, rank, prev = [], 0, None
    for pos, e in enumerate(ordered, start=1):
        if e["value"] != prev:
            rank, prev = pos, e["value"]
        out.append({**e, "rank": rank})
    return out


def _aggregates(db: Session, contest: Contest):
    stories = db.scalars(
        select(Story)
        .where(Story.contest_id == contest.id, Story.anon_number.is_not(None))
        .options(selectinload(Story.author))
    ).all()
    rows = db.execute(
        select(Rating.story_id, func.count(Rating.id), *[func.avg(getattr(Rating, k)) for k in SCALE_KEYS])
        .join(Story, Story.id == Rating.story_id)
        .where(Story.contest_id == contest.id)
        .group_by(Rating.story_id)
    ).all()
    avg = {
        r[0]: {"votes": r[1], **{k: round(float(r[2 + i]), 2) for i, k in enumerate(SCALE_KEYS)}}
        for r in rows
    }
    star_rows = db.execute(
        select(Star.story_id, func.count(Star.id)).where(Star.contest_id == contest.id).group_by(Star.story_id)
    ).all()
    stars = {r[0]: r[1] for r in star_rows}
    return stories, avg, stars


def compute_results(db: Session, contest: Contest) -> dict:
    stories, avg, stars = _aggregates(db, contest)

    scales = []
    for key, label, _ in SCALES:
        entries = [
            {
                "anon_number": s.anon_number,
                "title": s.title,
                "author": s.author.nickname,
                "value": avg[s.id][key],
                "votes": avg[s.id]["votes"],
            }
            for s in stories
            if s.id in avg
        ]
        scales.append({"key": key, "label": label, "ranking": _ranked(entries, True)})

    star_entries = [
        {
            "anon_number": s.anon_number,
            "title": s.title,
            "author": s.author.nickname,
            "value": stars[s.id],
            "votes": avg.get(s.id, {}).get("votes", 0),
        }
        for s in stories
        if s.id in stars
    ]
    return {
        "scales": scales,
        "stars": {"ranking": _ranked(star_entries, False)},
        "totals": {
            "stories": len(stories),
            "ratings": sum(a["votes"] for a in avg.values()),
            "stars": sum(stars.values()),
        },
        "survey": survey_stats(
            db.scalars(
                select(Survey).join(Story, Story.id == Survey.story_id).where(Story.contest_id == contest.id)
            ).all()
        ),
    }


def story_reviews(db: Session, story: Story) -> list[dict]:
    """Рецензии на рассказ БЕЗ авторов, id и времени.

    Порядок перемешан (детерминированно для рассказа): порядок id совпадал бы с порядком
    написания, а он не должен ничего говорить о рецензентах.
    """
    bodies = db.scalars(select(Review.body).where(Review.story_id == story.id).order_by(Review.id)).all()
    random.Random(story.id).shuffle(bodies)
    return [{"body": b} for b in bodies]


def story_result(db: Session, contest: Contest, story: Story) -> dict:
    _, avg, stars = _aggregates(db, contest)
    a = avg.get(story.id)
    return {
        "anon_number": story.anon_number,
        "title": story.title,
        "body": story.body,
        "disclaimer": story.disclaimer,
        "author": story.author.nickname,
        "votes": a["votes"] if a else 0,
        "scores": {k: a[k] for k in SCALE_KEYS} if a else None,
        "stars": stars.get(story.id, 0),
        "reviews": story_reviews(db, story),
        "survey": survey_stats(db.scalars(select(Survey).where(Survey.story_id == story.id)).all()),
    }
