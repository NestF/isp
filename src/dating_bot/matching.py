from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, case, func, not_, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from dating_bot.config import Config
from dating_bot.models import UserProfile, Vote


def _is_missing_rating_column(exc: Exception) -> bool:
    msg = str(exc).lower()
    return ("rating_score" in msg) and (
        ("does not exist" in msg) or ("undefined column" in msg) or ("no such column" in msg)
    )


async def _execute_with_fallback(session: AsyncSession, primary, fallback):
    try:
        return await session.execute(primary)
    except DBAPIError as e:
        if fallback is not None and _is_missing_rating_column(e):
            return await session.execute(fallback)
        raise


def _apply_pref_filters(query, viewer: UserProfile):
    pref_age_min = int(getattr(viewer, "pref_age_min", 18) or 18)
    pref_age_max = int(getattr(viewer, "pref_age_max", 100) or 100)
    query = query.where(UserProfile.age.between(pref_age_min, pref_age_max))
    if getattr(viewer, "pref_gender", None):
        query = query.where(UserProfile.gender == viewer.pref_gender)
    if getattr(viewer, "pref_city", None):
        query = query.where(UserProfile.city == viewer.pref_city)
    return query


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

    base_pref = _apply_pref_filters(base, viewer)
    base_all = base

    if cache:
        cached_id = await cache.get_candidate(int(viewer.tg_id))
        if cached_id:
            q0 = base_pref.where(UserProfile.tg_id == int(cached_id)).limit(1)
            res0 = await session.execute(q0)
            cand0 = res0.scalar_one_or_none()
            if cand0:
                return cand0
            await cache.del_candidate(int(viewer.tg_id))

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base_pref.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.rating_score.desc(), UserProfile.updated_at.desc())
            .limit(1)
        )
        q_fallback = (
            base_pref.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.updated_at.desc())
            .limit(1)
        )
        res = await _execute_with_fallback(session, q, q_fallback)
        cand = res.scalar_one_or_none()
        if cand:
            if cache:
                await cache.set_candidate(int(viewer.tg_id), int(cand.tg_id))
            return cand
        delta += cfg.age_delta_step

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base_all.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.rating_score.desc(), UserProfile.updated_at.desc())
            .limit(1)
        )
        q_fallback = (
            base_all.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.updated_at.desc())
            .limit(1)
        )
        res = await _execute_with_fallback(session, q, q_fallback)
        cand = res.scalar_one_or_none()
        if cand:
            if cache:
                await cache.set_candidate(int(viewer.tg_id), int(cand.tg_id))
            return cand
        delta += cfg.age_delta_step

    same_city_bonus = case((UserProfile.city == viewer.city, cfg.city_bonus), else_=0.0)
    age_part = cfg.age_weight * (1.0 / (1.0 + func.abs(UserProfile.age - viewer.age)))
    rating_delta = UserProfile.rating_score - cfg.rating_initial
    rating_part = cfg.rating_weight * rating_delta
    score = same_city_bonus + age_part + rating_part

    q2 = base_pref.order_by(score.desc(), UserProfile.combined_score.desc()).limit(1)
    q2_fallback = base_pref.order_by((same_city_bonus + age_part).desc(), UserProfile.combined_score.desc()).limit(1)
    res = await _execute_with_fallback(session, q2, q2_fallback)
    cand = res.scalar_one_or_none()
    if not cand:
        q3 = base_all.order_by(score.desc(), UserProfile.combined_score.desc()).limit(1)
        q3_fallback = base_all.order_by((same_city_bonus + age_part).desc(), UserProfile.combined_score.desc()).limit(1)
        res3 = await _execute_with_fallback(session, q3, q3_fallback)
        cand = res3.scalar_one_or_none()
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

    base_pref = _apply_pref_filters(base, viewer)
    base_all = base

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base_pref.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.rating_score.desc(), UserProfile.updated_at.desc())
            .limit(limit)
        )
        q_fallback = (
            base_pref.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.updated_at.desc())
            .limit(limit)
        )
        res = await _execute_with_fallback(session, q, q_fallback)
        ids = [int(x) for x in res.scalars().all()]
        if ids:
            return ids
        delta += cfg.age_delta_step

    delta = cfg.age_delta_start
    while delta <= cfg.age_delta_max:
        q = (
            base_all.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.rating_score.desc(), UserProfile.updated_at.desc())
            .limit(limit)
        )
        q_fallback = (
            base_all.where(func.abs(UserProfile.age - viewer.age) <= delta)
            .order_by(UserProfile.combined_score.desc(), UserProfile.updated_at.desc())
            .limit(limit)
        )
        res = await _execute_with_fallback(session, q, q_fallback)
        ids = [int(x) for x in res.scalars().all()]
        if ids:
            return ids
        delta += cfg.age_delta_step

    same_city_bonus = case((UserProfile.city == viewer.city, cfg.city_bonus), else_=0.0)
    age_part = cfg.age_weight * (1.0 / (1.0 + func.abs(UserProfile.age - viewer.age)))
    rating_delta = UserProfile.rating_score - cfg.rating_initial
    rating_part = cfg.rating_weight * rating_delta
    score = same_city_bonus + age_part + rating_part

    q2 = base_pref.order_by(score.desc(), UserProfile.combined_score.desc()).limit(limit)
    q2_fallback = base_pref.order_by((same_city_bonus + age_part).desc(), UserProfile.combined_score.desc()).limit(limit)
    res2 = await _execute_with_fallback(session, q2, q2_fallback)
    ids2 = [int(x) for x in res2.scalars().all()]
    if ids2:
        return ids2

    q3 = base_all.order_by(score.desc(), UserProfile.combined_score.desc()).limit(limit)
    q3_fallback = base_all.order_by((same_city_bonus + age_part).desc(), UserProfile.combined_score.desc()).limit(limit)
    res3 = await _execute_with_fallback(session, q3, q3_fallback)
    return [int(x) for x in res3.scalars().all()]
