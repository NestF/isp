import asyncio

from celery import shared_task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from dating_bot.config import load_config
from dating_bot.models import Base, UserProfile
from dating_bot.repository import recompute_scores


async def _recompute_all():
    cfg = load_config()
    engine = create_async_engine(cfg.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        res = await session.execute(select(UserProfile.tg_id))
        ids = [int(x) for x in res.scalars().all()]
        for tg_id in ids:
            await recompute_scores(session, cfg, tg_id)
        await session.commit()

    await engine.dispose()


@shared_task(name="dating_bot.tasks.recompute_all_ratings")
def recompute_all_ratings():
    asyncio.run(_recompute_all())

