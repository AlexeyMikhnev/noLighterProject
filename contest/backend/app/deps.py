from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import Contest, User
from .security import decode_token
from .services import current_contest

_bearer = HTTPBearer(auto_error=False)

PHASE_NAMES = {
    "draft": "подготовка",
    "submission": "приём работ",
    "voting": "оценивание",
    "results": "результаты",
}


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    user_id = decode_token(creds.credentials) if creds else None
    user = db.get(User, user_id) if user_id else None
    if not user:
        raise HTTPException(401, "Требуется вход")
    return user


def require_organizer(user: User = Depends(get_current_user)) -> User:
    if user.role != "organizer":
        raise HTTPException(403, "Только для организатора")
    return user


def require_participant(user: User = Depends(get_current_user)) -> User:
    if user.role == "organizer":
        raise HTTPException(403, "Организатор не участвует в конкурсе")
    return user


def get_contest(db: Session = Depends(get_db)) -> Contest:
    contest = current_contest(db)
    if not contest:
        raise HTTPException(404, "Конкурс ещё не создан")
    return contest


def require_phase(*phases: str):
    """Проверка фазы НА СЕРВЕРЕ: именно здесь закрываются правки и доступ к чужим работам."""

    def dep(contest: Contest = Depends(get_contest)) -> Contest:
        if contest.phase not in phases:
            raise HTTPException(
                403,
                f"Недоступно в текущей фазе («{PHASE_NAMES[contest.phase]}»)",
            )
        return contest

    return dep
