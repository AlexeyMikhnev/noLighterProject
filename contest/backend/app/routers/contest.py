from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_current_user
from ..models import User
from ..services import contest_to_dict, current_contest

router = APIRouter(prefix="/api/contest", tags=["contest"])


@router.get("/current")
def get_current(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Текущий конкурс (или null). В черновике участники не видят даже темы."""
    contest = current_contest(db)
    return contest_to_dict(db, contest, user) if contest else None
