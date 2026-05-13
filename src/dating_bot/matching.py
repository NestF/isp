from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, case, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from dating_bot.config import Config
from dating_bot.models import UserProfile, Vote


async def pick_next_candidate(session: AsyncSession, cfg: Config, viewer: UserProfile, cache=None) -> Optional[UserProfile]:
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

    pref_age_min = int(getattr(viewer, "pref_age_min", 18) or 18)
    pref_age_max = int(getattr(viewer, "pref_age_max", 100) or 100)
    base = base.where(UserProfile.age.between(pref_age_min, pref_age_max))
    if getattr(viewer, "pref_gender", None):
        base = base.where(UserProfile.gender == viewer.pref_gender)
    if getattr(viewer, "pref_city", None):
        base = base.where(UserProfile.city == viewer.pref_city)

    if cache:
        cached_id = await cache.get_candidate(int(viewer.tg_id))
        if cached_id:
            q0 = base.where(UserProfile.tg_id == int(cached_id)).limit(1)
            res0 = await session.execute(q0)
            cand0 = res0.scalar_one_or_none()
            if cand0:
                return cand0
            await cache.del_candidate(int(viewer.tg_id))

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base.where(UserProfile.city == viewer.city)
            .where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.updated_at.desc())
            .limit(1)
        )
        res = await session.execute(q)
        cand = res.scalar_one_or_none()
        if cand:
            if cache:
                await cache.set_candidate(int(viewer.tg_id), int(cand.tg_id))
            return cand
        delta += cfg.age_delta_step

    same_city_bonus = case((UserProfile.city == viewer.city, cfg.city_bonus), else_=0.0)
    age_part = cfg.age_weight * (1.0 / (1.0 + func.abs(UserProfile.age - viewer.age)))
    rating_part = cfg.rating_weight * UserProfile.combined_score
    score = same_city_bonus + age_part + rating_part

    res = await session.execute(base.order_by(score.desc(), UserProfile.combined_score.desc()).limit(1))
    cand = res.scalar_one_or_none()
    if cand and cache:
        await cache.set_candidate(int(viewer.tg_id), int(cand.tg_id))
    return cand


async def build_candidate_batch(session: AsyncSession, cfg: Config, viewer: UserProfile, limit: int = 10) -> list[int]:
    base = (
        select(UserProfile.tg_id)
        .where(UserProfile.tg_id != viewer.tg_id)
        .where(
            not_(
                select(Vote.id)
                .where(and_(Vote.viewer_id == viewer.tg_id, Vote.target_id == UserProfile.tg_id))
                .exists()
            )
        )
    )

    pref_age_min = int(getattr(viewer, "pref_age_min", 18) or 18)
    pref_age_max = int(getattr(viewer, "pref_age_max", 100) or 100)
    base = base.where(UserProfile.age.between(pref_age_min, pref_age_max))
    if getattr(viewer, "pref_gender", None):
        base = base.where(UserProfile.gender == viewer.pref_gender)
    if getattr(viewer, "pref_city", None):
        base = base.where(UserProfile.city == viewer.pref_city)

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base.where(UserProfile.city == viewer.city)
            .where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.updated_at.desc())
            .limit(limit)
        )
        res = await session.execute(q)
        ids = [int(x) for x in res.scalars().all()]
        if ids:
            return ids
        delta += cfg.age_delta_step

    same_city_bonus = case((UserProfile.city == viewer.city, cfg.city_bonus), else_=0.0)
    age_part = cfg.age_weight * (1.0 / (1.0 + func.abs(UserProfile.age - viewer.age)))
    rating_part = cfg.rating_weight * UserProfile.combined_score
    score = same_city_bonus + age_part + rating_part

    q2 = base.order_by(score.desc(), UserProfile.combined_score.desc()).limit(limit)
    res2 = await session.execute(q2)
    return [int(x) for x in res2.scalars().all()]
