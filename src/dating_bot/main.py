import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from dotenv import load_dotenv

from dating_bot.config import load_config
from dating_bot.db import make_engine, make_session_factory
from dating_bot.handlers import router
from dating_bot.models import Base


async def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    cfg = load_config()

    engine = make_engine(cfg.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = make_session_factory(engine)

    storage = RedisStorage.from_url(cfg.redis_url)
    dp = Dispatcher(storage=storage)
    dp["cfg"] = cfg
    dp["session_factory"] = session_factory
    dp.include_router(router)

    bot = Bot(token=cfg.bot_token)
    await dp.start_polling(bot, drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.run(main())

