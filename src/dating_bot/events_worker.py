import asyncio
import json
import logging

import aio_pika
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from dating_bot.config import load_config
from dating_bot.models import Base
from dating_bot.repository import save_event


async def main():
    logging.basicConfig(level=logging.INFO)
    cfg = load_config()

    engine = create_async_engine(cfg.database_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    conn = await aio_pika.connect_robust(cfg.amqp_url)
    channel = await conn.channel()
    exchange = await channel.declare_exchange("dating.events", aio_pika.ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue("dating.events.queue", durable=True)
    await queue.bind(exchange, routing_key="dating.*")

    async with queue.iterator() as it:
        async for msg in it:
            async with msg.process():
                try:
                    data = json.loads(msg.body.decode("utf-8"))
                    event_type = data.get("event_type") or "unknown"
                    actor_id = data.get("actor_id")
                    target_id = data.get("target_id")
                    payload = data.get("payload") or {}
                except Exception:
                    continue

                async with session_factory() as session:
                    await save_event(session, event_type, actor_id, target_id, payload)
                    await session.commit()


if __name__ == "__main__":
    asyncio.run(main())

