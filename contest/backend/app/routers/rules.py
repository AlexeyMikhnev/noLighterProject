"""Правила конкурса: читать может кто угодно (в том числе до регистрации), править — организатор (см. admin.py)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..default_rules import DEFAULT_RULES_HTML
from ..models import Setting
from ..services_time import iso

router = APIRouter(prefix="/api/rules", tags=["rules"])

KEY = "rules"


def rules_out(db: Session) -> dict:
    row = db.get(Setting, KEY)
    if row is None:
        return {"body": DEFAULT_RULES_HTML, "updated_at": None, "is_default": True}
    return {"body": row.value, "updated_at": iso(row.updated_at), "is_default": False}


@router.get("")
def get_rules(db: Session = Depends(get_db)):
    """Публичный: HTML уже очищен при сохранении (белый список тегов без атрибутов)."""
    return rules_out(db)
