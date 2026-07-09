import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Reads DATABASE_URL from the environment (.env). If it's not set at all,
# falls back to local SQLite so the app still runs out of the box with no
# Postgres setup required. Once a real Postgres URL is added to .env
# (e.g. postgresql://user:password@host:5432/metacare), it's used automatically.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./metacare.db")

# SQLite needs this connect arg; Postgres/other DBs don't and will error if passed.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
