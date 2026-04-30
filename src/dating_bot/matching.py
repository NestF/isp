from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, case, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dating_bot.config import Config
from dating_bot.models import UserProfile, Vote


async def pick_next_candidate(session: AsyncSession, cfg: Config, viewer: UserProfile) -> Optional[UserProfile]:
    base = (
        select(UserProfile)
        .where(UserProfile.tg_id != viewer.tg_id)
        .where(
            not_(
                select(Vote.id)
                .where(and_(Vote.viewer_id == viewer.tg_id, Vote.target_id == UserProfile.tg_id))
                .exists()
            )
        )
    )

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base.where(UserProfile.city == viewer.city)
            .where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.rating_score.desc(), UserProfile.updated_at.desc())
            .limit(1)
        )
        res = await session.execute(q)
        cand = res.scalar_one_or_none()
        if cand:
            return cand
        delta += cfg.age_delta_step

    same_city_bonus = case((UserProfile.city == viewer.city, cfg.city_bonus), else_=0.0)
    age_part = cfg.age_weight * (1.0 / (1.0 + func.abs(UserProfile.age - viewer.age)))
    rating_part = cfg.rating_weight * UserProfile.rating_score
    score = same_city_bonus + age_part + rating_part

    res = await session.execute(base.order_by(score.desc(), UserProfile.rating_score.desc()).limit(1))
    return res.scalar_one_or_none()

