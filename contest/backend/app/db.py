from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from . import config

_is_sqlite = config.DATABASE_URL.startswith("sqlite")
engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Создаёт таблицы и, если нет ни одного организатора, заводит его из env."""
    from .models import User
    from .security import hash_password

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.role == "organizer").limit(1)) is None:
            db.add(
                User(
                    email=config.ADMIN_EMAIL.lower(),
                    nickname=config.ADMIN_NICKNAME,
                    password_hash=hash_password(config.ADMIN_PASSWORD),
                    role="organizer",
                )
            )
            db.commit()
