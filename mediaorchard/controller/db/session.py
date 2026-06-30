from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine


def create_db_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args)


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)


def session_scope(engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session

