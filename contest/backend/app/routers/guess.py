"""«Угадайка»: матрица «рассказ × возможный автор». Необязательная игра, на оценки и топы не влияет.

Правила анонимности:
- до фазы results сервер НЕ сообщает, верна ли отметка: иначе перебором можно вычислить всех авторов;
- в ответе фазы voting только ники приславших (алфавитно) и собственные отметки читателя,
  без связи «рассказ → автор» и без внутренних id;
- свой ник из столбцов и свой рассказ из строк убраны: вы точно знаете, что не писали чужое.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import require_participant, require_phase
from ..models import Contest, Guess, Story, User
from ..schemas import GuessRowIn
from ..services import my_detective_result
from .voting import _story, voter

router = APIRouter(prefix="/api/guess", tags=["guess"])


def viewer(
    user: User = Depends(require_participant),
    contest: Contest = Depends(require_phase("voting", "results")),
    db: Session = Depends(get_db),
) -> tuple[User, Contest]:
    """Смотреть матрицу можно в оценивании (с тем же правилом допуска) и после итогов."""
    if contest.phase == "voting" and contest.voters_must_submit:
        has_story = db.scalar(
            select(Story.id).where(Story.contest_id == contest.id, Story.author_id == user.id)
        )
        if has_story is None:
            raise HTTPException(403, "Угадывать могут только участники, приславшие свой рассказ")
    return user, contest


def _my_marks(db: Session, contest: Contest, user: User) -> dict[int, list[str]]:
    rows = db.execute(
        select(Story.anon_number, User.nickname)
        .select_from(Guess)
        .join(Story, Story.id == Guess.story_id)
        .join(User, User.id == Guess.guessed_user_id)
        .where(Guess.contest_id == contest.id, Guess.guesser_id == user.id)
    ).all()
    marks: dict[int, list[str]] = {}
    for anon_number, nickname in rows:
        marks.setdefault(anon_number, []).append(nickname)
    return {n: sorted(v, key=str.lower) for n, v in marks.items()}


@router.get("")
def matrix(ctx=Depends(viewer), db: Session = Depends(get_db)):
    user, contest = ctx
    stories = db.scalars(
        select(Story)
        .where(Story.contest_id == contest.id, Story.anon_number.is_not(None))
        .options(selectinload(Story.author))
        .order_by(Story.anon_number)
    ).all()
    candidates = sorted({s.author.nickname for s in stories if s.author_id != user.id}, key=str.lower)
    out = {
        "phase": contest.phase,
        "stories": [{"anon_number": s.anon_number, "title": s.title} for s in stories if s.author_id != user.id],
        "candidates": candidates,
        "marks": {str(n): v for n, v in _my_marks(db, contest, user).items()},
    }
    if contest.phase == "results":
        # Только теперь раскрывается, кто на самом деле автор, и считаются очки.
        out["truth"] = {str(s.anon_number): s.author.nickname for s in stories if s.author_id != user.id}
        out["result"] = my_detective_result(db, contest, user)
    return out


@router.put("/stories/{anon_number}")
def put_row(anon_number: int, data: GuessRowIn, ctx=Depends(voter), db: Session = Depends(get_db)):
    """Заменяет все отметки строки. Ответ не говорит, верны ли они."""
    user, contest = ctx
    story = _story(db, contest, user, anon_number)
    authors = dict(
        db.execute(
            select(User.nickname, User.id)
            .join(Story, Story.author_id == User.id)
            .where(Story.contest_id == contest.id)
        ).all()
    )
    wanted = set(data.nicknames)
    unknown = wanted - set(authors)
    if unknown:
        raise HTTPException(422, "Среди участников нет: " + ", ".join(sorted(unknown)))
    if user.nickname in wanted:
        raise HTTPException(422, "Себя отмечать нельзя: вы не автор чужого рассказа")
    db.execute(delete(Guess).where(Guess.story_id == story.id, Guess.guesser_id == user.id))
    for nickname in wanted:
        db.add(
            Guess(contest_id=contest.id, story_id=story.id, guesser_id=user.id, guessed_user_id=authors[nickname])
        )
    db.commit()
    return {"anon_number": anon_number, "nicknames": sorted(wanted, key=str.lower)}
