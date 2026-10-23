import re
from datetime import datetime
from html import escape

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import SURVEY_BOOL_KEYS, SURVEY_BY_KEY, MAX_BODY_CHARS, MAX_BODY_HTML_CHARS, MAX_DISCLAIMER_CHARS, MAX_REVIEW_CHARS, MAX_TITLE_CHARS
from .richtext import analyze
from .services_time import to_naive_utc

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class RegisterIn(BaseModel):
    invite_token: str = Field(min_length=8, max_length=64)
    email: str = Field(max_length=255)
    nickname: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Некорректный email")
        return v

    @field_validator("nickname")
    @classmethod
    def _nick(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Псевдоним слишком короткий")
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class StoryIn(BaseModel):
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    body: str = Field(min_length=1, max_length=MAX_BODY_HTML_CHARS)
    disclaimer: str = Field(default="", max_length=MAX_DISCLAIMER_CHARS)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название не может быть пустым")
        return v

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = v.replace("\r\n", "\n").strip()
        if "<" not in v:
            # обычный текст (не из редактора): пустая строка делит абзацы, иначе они склеились бы
            v = "".join(f"<p>{escape(p.strip(), quote=False).replace(chr(10), "<br>")}</p>" for p in v.split("\n\n") if p.strip())
        # В базу и в ответы API попадает только результат очистки по белому списку тегов.
        html, chars = analyze(v)
        if chars == 0:
            raise ValueError("Текст не может быть пустым")
        if chars > MAX_BODY_CHARS:
            raise ValueError(f"Текст длиннее {MAX_BODY_CHARS} знаков (сейчас {chars})")
        return html

    @field_validator("disclaimer")
    @classmethod
    def _disclaimer(cls, v: str) -> str:
        return v.replace("\r\n", "\n").strip()


class RatingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impression: int = Field(ge=1, le=5)
    theme: int = Field(ge=1, le=5)
    style: int = Field(ge=1, le=5)
    mood: int = Field(ge=1, le=5)
    adventure: int = Field(ge=1, le=5)


def _option_keys(question: str) -> set[str]:
    return {k for k, _ in SURVEY_BY_KEY[question]["options"]}


class SurveyIn(BaseModel):
    """Все поля необязательны: пустой список / null = «не ответил»."""

    model_config = ConfigDict(extra="forbid")

    genres: list[str] = []
    settings: list[str] = []
    hero_gender: str | None = None
    about_children: bool | None = None
    about_animals: bool | None = None
    someone_died: bool | None = None
    has_guns: bool | None = None

    @field_validator("genres", "settings")
    @classmethod
    def _multi(cls, v: list[str], info) -> list[str]:
        allowed = _option_keys(info.field_name)
        bad = [x for x in v if x not in allowed]
        if bad:
            raise ValueError(f"Неизвестные варианты: {', '.join(bad)}")
        return list(dict.fromkeys(v))  # без повторов, порядок сохраняется

    @field_validator("hero_gender")
    @classmethod
    def _single(cls, v: str | None) -> str | None:
        if v is not None and v not in _option_keys("hero_gender"):
            raise ValueError("Неизвестный вариант")
        return v

    def is_empty(self) -> bool:
        """Ничего не отвечено. Осторожно: False у булевых — это ответ «нет», а не пустота."""
        return (
            not self.genres
            and not self.settings
            and self.hero_gender is None
            and all(getattr(self, k) is None for k in SURVEY_BOOL_KEYS)
        )


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=MAX_REVIEW_CHARS)

    @field_validator("body")
    @classmethod
    def _body(cls, v: str) -> str:
        v = v.replace("\r\n", "\n").strip()
        if not v:
            raise ValueError("Рецензия не может быть пустой")
        return v


class _Deadlines(BaseModel):
    @field_validator("submission_ends_at", "voting_ends_at", check_fields=False)
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        # Без часового пояса считаем, что время уже в UTC.
        return to_naive_utc(v)


class ContestCreateIn(_Deadlines):
    theme: str = Field(min_length=1, max_length=300)
    submission_ends_at: datetime | None = None
    voting_ends_at: datetime | None = None
    voters_must_submit: bool = True


class ContestPatchIn(_Deadlines):
    theme: str | None = Field(default=None, min_length=1, max_length=300)
    submission_ends_at: datetime | None = None
    voting_ends_at: datetime | None = None
    voters_must_submit: bool | None = None


class InvitesIn(BaseModel):
    count: int = Field(default=1, ge=1, le=50)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)
