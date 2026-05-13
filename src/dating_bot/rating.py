from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from dating_bot.config import Config
from dating_bot.repository import apply_match_bonus, ensure_match, inc_dislike, inc_like, is_mutual_like, recompute_scores, set_vote


async def vote_like(session: AsyncSession, cfg: Config, viewer_id: int, target_id: int, publisher=None) -> bool:
    await set_vote(session, viewer_id, target_id, "like")
    await inc_like(session, target_id, cfg.like_bonus)
    await recompute_scores(session, cfg, target_id)
    if publisher:
        await publisher.publish("like", viewer_id, target_id, {})

    mutual = await is_mutual_like(session, viewer_id, target_id)
    if mutual:
        created = await ensure_match(session, viewer_id, target_id)
        if created:
            await apply_match_bonus(session, viewer_id, target_id, cfg.match_bonus)
            await recompute_scores(session, cfg, viewer_id)
            await recompute_scores(session, cfg, target_id)
            if publisher:
                await publisher.publish("match", viewer_id, target_id, {"created": True})
        return created
    return False


async def vote_dislike(session: AsyncSession, cfg: Config, viewer_id: int, target_id: int, publisher=None) -> None:
    await set_vote(session, viewer_id, target_id, "dislike")
    await inc_dislike(session, target_id, cfg.dislike_penalty)
    await recompute_scores(session, cfg, target_id)
    if publisher:
        await publisher.publish("dislike", viewer_id, target_id, {})
