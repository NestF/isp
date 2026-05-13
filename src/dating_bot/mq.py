import json
from typing import Optional

import aio_pika


class EventPublisher:
    def __init__(self, amqp_url: str):
        self.amqp_url = amqp_url
        self._conn: Optional[aio_pika.RobustConnection] = None
        self._channel: Optional[aio_pika.abc.AbstractRobustChannel] = None
        self._exchange: Optional[aio_pika.abc.AbstractRobustExchange] = None

    async def connect(self):
        self._conn = await aio_pika.connect_robust(self.amqp_url)
        self._channel = await self._conn.channel()
        self._exchange = await self._channel.declare_exchange("dating.events", aio_pika.ExchangeType.TOPIC, durable=True)

    async def close(self):
        if self._conn:
            await self._conn.close()

    async def publish(self, event_type: str, actor_id: int | None, target_id: int | None, payload: dict):
        if not self._exchange:
            return
        body = json.dumps(
            {"event_type": event_type, "actor_id": actor_id, "target_id": target_id, "payload": payload},
            ensure_ascii=False,
        ).encode("utf-8")
        msg = aio_pika.Message(body=body, content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT)
        await self._exchange.publish(msg, routing_key=f"dating.{event_type}")

