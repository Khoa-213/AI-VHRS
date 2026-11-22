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
    # Small pool: Supabase's session pooler caps concurrent clients (DB_POOL_SIZE / DB_MAX_OVERFLOW).
    s = get_settings()
    return create_engine(s.sqlalchemy_url, pool_size=s.db_pool_size, max_overflow=s.db_max_overflow, pool_pre_ping=True)


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
    """Expose the acting account / reason to the DB triggers (status_histories, BR-16). One statement: each round trip to
    Supabase costs ~60 ms from the dev machine (docs/TEST_SPEEDUP_PLAN.md)."""
    session.execute(text("select set_config('app.current_account_id', :a, true), set_config('app.status_reason', :r, true)"),
                    {"a": "" if account_id is None else str(account_id), "r": reason or ""})
