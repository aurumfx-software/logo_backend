from typing import Generator
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.core.config import settings

# In SQLite (e.g. during testing), check_same_thread needs to be False
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine_kwargs = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
}

if not settings.DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update({
        "pool_size": 2,
        "max_overflow": 0,
        "pool_timeout": 30,
        "pool_recycle": 1800,
    })

engine = create_engine(
    settings.DATABASE_URL,
    **engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


_source_pool_ready = False


def ensure_wallet_source_pool(db: Session) -> None:
    """Add wallet_transactions.source_pool when the live table was created before that column."""
    global _source_pool_ready
    if _source_pool_ready or db.info.get("source_pool_ready"):
        db.info["source_pool_ready"] = True
        _source_pool_ready = True
        return
    conn = db.connection()
    inspector = inspect(conn)
    if "wallet_transactions" not in inspector.get_table_names():
        db.info["source_pool_ready"] = True
        return
    existing = {column["name"] for column in inspector.get_columns("wallet_transactions")}
    if "source_pool" not in existing:
        conn.execute(text("ALTER TABLE wallet_transactions ADD COLUMN source_pool VARCHAR(32)"))
        db.commit()
    db.info["source_pool_ready"] = True
    _source_pool_ready = True


def get_db() -> Generator[Session, None, None]:
    """Dependency that yields a database session and safely closes it."""
    db = SessionLocal()
    try:
        ensure_wallet_source_pool(db)
        yield db
    finally:
        db.close()
