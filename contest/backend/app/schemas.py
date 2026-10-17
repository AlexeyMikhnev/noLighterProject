import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .config import MAX_BODY_CHARS, MAX_REVIEW_CHARS, MAX_TITLE_CHARS
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
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)

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
        if not v:
            raise ValueError("Текст не может быть пустым")
        return v


class RatingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    impression: int = Field(ge=1, le=5)
    theme: int = Field(ge=1, le=5)
    style: int = Field(ge=1, le=5)
    light: int = Field(ge=1, le=5)
    dark: int = Field(ge=1, le=5)
    adventure: int = Field(ge=1, le=5)


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
