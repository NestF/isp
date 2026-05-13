from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker


def make_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, echo=False)


def make_session_factory(engine: AsyncEngine) -> sessionmaker:
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

