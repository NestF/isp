from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dating_bot.models import Match, UserProfile, Vote


async def get_profile(session: AsyncSession, tg_id: int) -> Optional[UserProfile]:
    res = await session.execute(select(UserProfile).where(UserProfile.tg_id == tg_id))
    return res.scalar_one_or_none()


async def upsert_profile(session: AsyncSession, data: dict) -> UserProfile:
    tg_id = int(data["tg_id"])
    profile = await get_profile(session, tg_id)
    if profile:
        for k, v in data.items():
            if hasattr(profile, k):
                setattr(profile, k, v)
    else:
        profile = UserProfile(**data)
        session.add(profile)
    await session.flush()
    return profile


async def delete_profile(session: AsyncSession, tg_id: int) -> None:
    await session.execute(delete(UserProfile).where(UserProfile.tg_id == tg_id))


async def has_vote(session: AsyncSession, viewer_id: int, target_id: int) -> bool:
    res = await session.execute(select(exists().where(and_(Vote.viewer_id == viewer_id, Vote.target_id == target_id))))
    return bool(res.scalar())


async def set_vote(session: AsyncSession, viewer_id: int, target_id: int, value: str) -> None:
    await session.execute(delete(Vote).where(and_(Vote.viewer_id == viewer_id, Vote.target_id == target_id)))
    session.add(Vote(viewer_id=viewer_id, target_id=target_id, value=value))


async def is_mutual_like(session: AsyncSession, viewer_id: int, target_id: int) -> bool:
    res = await session.execute(
        select(
            exists().where(and_(Vote.viewer_id == target_id, Vote.target_id == viewer_id, Vote.value == "like"))
        )
    )
    return bool(res.scalar())


async def ensure_match(session: AsyncSession, a: int, b: int) -> bool:
    u1, u2 = (a, b) if a < b else (b, a)
    res = await session.execute(select(exists().where(and_(Match.user1_id == u1, Match.user2_id == u2))))
    if res.scalar():
        return False

    session.add(Match(user1_id=u1, user2_id=u2))
    await session.execute(
        update(UserProfile).where(UserProfile.tg_id.in_([a, b])).values(matches_count=UserProfile.matches_count + 1)
    )
    return True


async def inc_like(session: AsyncSession, target_id: int, bonus: float) -> None:
    await session.execute(
        update(UserProfile)
        .where(UserProfile.tg_id == target_id)
        .values(
            likes_count=UserProfile.likes_count + 1,
            rating_score=func.greatest(0.0, UserProfile.rating_score + bonus),
        )
    )


async def inc_dislike(session: AsyncSession, target_id: int, penalty: float) -> None:
    await session.execute(
        update(UserProfile)
        .where(UserProfile.tg_id == target_id)
        .values(
            dislikes_count=UserProfile.dislikes_count + 1,
            rating_score=func.greatest(0.0, UserProfile.rating_score - penalty),
        )
    )


async def apply_match_bonus(session: AsyncSession, a: int, b: int, bonus: float) -> None:
    await session.execute(
        update(UserProfile)
        .where(UserProfile.tg_id.in_([a, b]))
        .values(rating_score=func.greatest(0.0, UserProfile.rating_score + bonus))
    )


async def top_profiles(session: AsyncSession, limit: int, min_events: int) -> list[UserProfile]:
    events = UserProfile.likes_count + UserProfile.dislikes_count + UserProfile.matches_count
    res = await session.execute(
        select(UserProfile)
        .where(events >= min_events)
        .order_by(UserProfile.rating_score.desc(), UserProfile.matches_count.desc())
        .limit(limit)
    )
    return list(res.scalars().all())


async def get_matches(session: AsyncSession, tg_id: int) -> list[UserProfile]:
    res = await session.execute(
        select(Match.user1_id, Match.user2_id).where(or_(Match.user1_id == tg_id, Match.user2_id == tg_id))
    )
    pairs = res.all()
    if not pairs:
        return []

    other_ids = []
    for u1, u2 in pairs:
        other_ids.append(int(u2 if int(u1) == int(tg_id) else u1))

    res2 = await session.execute(select(UserProfile).where(UserProfile.tg_id.in_(other_ids)).order_by(UserProfile.updated_at.desc()))
    return list(res2.scalars().all())
