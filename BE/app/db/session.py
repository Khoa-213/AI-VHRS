"""Engine / session factory. One transaction per request (commit on success)."""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine() -> Engine:
    # Small pool: Supabase's session pooler caps concurrent clients.
    return create_engine(get_settings().sqlalchemy_url, pool_size=3, max_overflow=2, pool_pre_ping=True)


@lru_cache
def _factory() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_actor(session: Session, account_id: int | None, reason: str | None = None) -> None:
    """Expose the acting account / reason to the DB triggers (status_histories, BR-16)."""
    session.execute(text("select set_config('app.current_account_id', :a, true)"),
                    {"a": "" if account_id is None else str(account_id)})
    session.execute(text("select set_config('app.status_reason', :r, true)"), {"r": reason or ""})
