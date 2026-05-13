import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from dotenv import load_dotenv
from redis.asyncio import Redis, ConnectionError as RedisConnectionError
from sqlalchemy import text

from dating_bot.cache import ProfileCache
from dating_bot.config import load_config
from dating_bot.db import make_engine, make_session_factory
from dating_bot.handlers import router
from dating_bot.mq import EventPublisher
from dating_bot.models import Base


async def ensure_schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS gender VARCHAR(16)"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS interests JSONB NOT NULL DEFAULT '[]'::jsonb"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS pref_age_min INTEGER NOT NULL DEFAULT 18"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS pref_age_max INTEGER NOT NULL DEFAULT 100"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS pref_gender VARCHAR(16)"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS pref_city VARCHAR(128)"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS primary_score DOUBLE PRECISION NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS behavior_score DOUBLE PRECISION NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS combined_score DOUBLE PRECISION NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS referral_score DOUBLE PRECISION NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS rating_score DOUBLE PRECISION NOT NULL DEFAULT 1000.0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS dialogs_count INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS referrals_count INTEGER NOT NULL DEFAULT 0"))
        await conn.execute(text("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS referred_by BIGINT"))

        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_profiles_combined_score ON user_profiles (combined_score)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_profiles_rating_score ON user_profiles (rating_score)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_profiles_pref_city ON user_profiles (pref_city)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_profiles_gender ON user_profiles (gender)"))


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()

    engine = make_engine(cfg.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_schema(engine)

    session_factory = make_session_factory(engine)

    storage = RedisStorage.from_url(cfg.redis_url)
    cache = None
    try:
        redis = Redis.from_url(cfg.redis_url, decode_responses=True)
        await redis.ping()
        cache = ProfileCache(redis=redis, ttl_sec=cfg.cache_ttl_sec)
    except (RedisConnectionError, OSError):
        cache = None

    publisher = EventPublisher(cfg.amqp_url)
    try:
        await publisher.connect()
    except Exception:
        publisher = None

    dp = Dispatcher(storage=storage)
    dp["cfg"] = cfg
    dp["session_factory"] = session_factory
    dp["cache"] = cache
    dp["publisher"] = publisher
    dp.include_router(router)

    bot = Bot(token=cfg.bot_token)
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())
