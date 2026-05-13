import json
from typing import Optional


class ProfileCache:
    def __init__(self, redis, ttl_sec: int):
        self.redis = redis
        self.ttl_sec = ttl_sec

    async def get_profile(self, tg_id: int) -> Optional[dict]:
        if not self.redis:
            return None
        raw = await self.redis.get(f"profile:{tg_id}")
        if not raw:
            return None
        return json.loads(raw)

    async def set_profile(self, tg_id: int, profile: dict):
        if not self.redis:
            return
        await self.redis.setex(f"profile:{tg_id}", self.ttl_sec, json.dumps(profile, ensure_ascii=False))

    async def del_profile(self, tg_id: int):
        if not self.redis:
            return
        await self.redis.delete(f"profile:{tg_id}")

    async def get_candidate(self, viewer_id: int) -> Optional[int]:
        if not self.redis:
            return None
        raw = await self.redis.get(f"candidate:{viewer_id}")
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    async def set_candidate(self, viewer_id: int, target_id: int):
        if not self.redis:
            return
        await self.redis.setex(f"candidate:{viewer_id}", self.ttl_sec, str(int(target_id)))

    async def del_candidate(self, viewer_id: int):
        if not self.redis:
            return
        await self.redis.delete(f"candidate:{viewer_id}")

    async def queue_len(self, viewer_id: int) -> int:
        if not self.redis:
            return 0
        n = await self.redis.llen(f"candidates:{viewer_id}")
        return int(n or 0)

    async def pop_next(self, viewer_id: int) -> Optional[int]:
        if not self.redis:
            return None
        raw = await self.redis.lpop(f"candidates:{viewer_id}")
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            return None

    async def replace_queue(self, viewer_id: int, candidate_ids: list[int]):
        if not self.redis:
            return
        key = f"candidates:{viewer_id}"
        await self.redis.delete(key)
        if not candidate_ids:
            return
        await self.redis.rpush(key, *[str(int(x)) for x in candidate_ids])
        await self.redis.expire(key, self.ttl_sec)

    async def clear_queue(self, viewer_id: int):
        if not self.redis:
            return
        await self.redis.delete(f"candidates:{viewer_id}")
