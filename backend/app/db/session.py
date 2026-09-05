from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from ..core.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine():
    url = get_settings().database_url
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})


engine = _engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
