from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import SCALE_KEYS
from .db import Base
from .services_time import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nickname: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="participant")  # organizer | participant
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Invite(Base):
    """Одноразовая ссылка-приглашение: /register/<token>."""

    __tablename__ = "invites"

    token: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User | None"] = relationship()


class Contest(Base):
    __tablename__ = "contests"

    id: Mapped[int] = mapped_column(primary_key=True)
    theme: Mapped[str] = mapped_column(String(300))
    # draft -> submission -> voting -> results
    phase: Mapped[str] = mapped_column(String(16), default="draft")
    submission_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    voting_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Оценивать могут только те, кто сам прислал рассказ (защита от «пустых» аккаунтов).
    voters_must_submit: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setting(Base):
    """Настройки сайта «ключ — значение». Пока одна: текст правил (key="rules", HTML после очистки)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Story(Base):
    __tablename__ = "stories"
    __table_args__ = (
        UniqueConstraint("contest_id", "author_id", name="uq_story_author"),
        UniqueConstraint("contest_id", "anon_number", name="uq_story_anon"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    # Предупреждение автора читателям (жанр, возрастные ограничения и т. п.), может быть пустым.
    disclaimer: Mapped[str] = mapped_column(Text, default="")
    # Случайный номер, присваивается при старте голосования. Наружу до финала
    # отдаётся ТОЛЬКО он: id и время загрузки выдали бы порядок отправки.
    anon_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    author: Mapped[User] = relationship()


class Rating(Base):
    """Оценка рассказа одним участником сразу по всем шкалам (1..5)."""

    __tablename__ = "ratings"
    __table_args__ = (
        UniqueConstraint("story_id", "rater_id", name="uq_rating"),
        *[CheckConstraint(f"{k} BETWEEN 1 AND 5", name=f"ck_rating_{k}") for k in SCALE_KEYS],
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    impression: Mapped[int] = mapped_column(Integer)
    theme: Mapped[int] = mapped_column(Integer)
    style: Mapped[int] = mapped_column(Integer)
    mood: Mapped[int] = mapped_column(Integer)
    adventure: Mapped[int] = mapped_column(Integer)


class Survey(Base):
    """Опросник читателя о рассказе (для статистики). Не влияет на оценки и топы.

    Пустое значение (пустой список / NULL) = «не ответил». Наружу уходят только агрегаты по рассказу.
    """

    __tablename__ = "surveys"
    __table_args__ = (UniqueConstraint("story_id", "rater_id", name="uq_survey"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    genres: Mapped[list] = mapped_column(JSON, default=list)
    settings: Mapped[list] = mapped_column(JSON, default=list)
    hero_gender: Mapped[str | None] = mapped_column(String(16), nullable=True)
    about_children: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    about_animals: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    someone_died: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    has_guns: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Star(Base):
    """Звезда: у каждого участника их STARS_PER_USER, по одной на рассказ."""

    __tablename__ = "stars"
    __table_args__ = (UniqueConstraint("story_id", "giver_id", name="uq_star"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contest_id: Mapped[int] = mapped_column(ForeignKey("contests.id"), index=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    giver_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class Review(Base):
    """Анонимная рецензия на рассказ. Одна на пару (рассказ, рецензент).

    reviewer_id хранится только для того, чтобы рецензент мог править/удалять свою рецензию
    и видеть её в личном кабинете. Наружу автор рецензии не отдаётся НИКОГДА, даже в финале.
    """

    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("story_id", "reviewer_id", name="uq_review"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("stories.id"), index=True)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
