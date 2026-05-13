from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, delete, exists, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from dating_bot.models import InteractionEvent, Match, ProfileRating, UserProfile, Vote
from dating_bot.ranking import compute_behavior_score, compute_combined_score, compute_primary_score


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


def profile_to_dict(p: UserProfile) -> dict:
    return {
        "tg_id": int(p.tg_id),
        "username": p.username,
        "full_name": p.full_name,
        "age": int(p.age),
        "city": p.city,
        "gender": p.gender,
        "bio": p.bio,
        "interests": list(p.interests or []),
        "pref_age_min": int(p.pref_age_min),
        "pref_age_max": int(p.pref_age_max),
        "pref_gender": p.pref_gender,
        "pref_city": p.pref_city,
        "media": list(p.media or []),
        "primary_score": float(p.primary_score),
        "behavior_score": float(p.behavior_score),
        "combined_score": float(p.combined_score),
        "referral_score": float(p.referral_score),
        "rating_score": float(p.rating_score),
        "likes_count": int(p.likes_count),
        "dislikes_count": int(p.dislikes_count),
        "matches_count": int(p.matches_count),
        "dialogs_count": int(p.dialogs_count),
        "referrals_count": int(p.referrals_count),
        "referred_by": int(p.referred_by) if p.referred_by is not None else None,
    }


async def recompute_scores(session: AsyncSession, cfg, tg_id: int):
    p = await get_profile(session, tg_id)
    if not p:
        return
    d = profile_to_dict(p)
    primary = compute_primary_score(d, cfg)
    behavior = compute_behavior_score(d)
    d["primary_score"] = primary
    d["behavior_score"] = behavior
    d["combined_score"] = compute_combined_score(d, cfg)
    await session.execute(
        update(UserProfile)
        .where(UserProfile.tg_id == tg_id)
        .values(
            primary_score=d["primary_score"],
            behavior_score=d["behavior_score"],
            combined_score=d["combined_score"],
        )
    )
    await session.execute(
        delete(ProfileRating).where(ProfileRating.tg_id == tg_id)
    )
    session.add(
        ProfileRating(
            tg_id=tg_id,
            primary_score=d["primary_score"],
            behavior_score=d["behavior_score"],
            referral_score=float(d.get("referral_score") or 0.0),
            combined_score=d["combined_score"],
        )
    )


async def save_event(session: AsyncSession, event_type: str, actor_id: int | None, target_id: int | None, payload: dict):
    session.add(InteractionEvent(event_type=event_type, actor_id=actor_id, target_id=target_id, payload=payload))


async def add_referral(session: AsyncSession, cfg, referrer_id: int, bonus: float = 10.0):
    await session.execute(
        update(UserProfile)
        .where(UserProfile.tg_id == referrer_id)
        .values(
            referrals_count=UserProfile.referrals_count + 1,
            referral_score=func.greatest(0.0, UserProfile.referral_score + bonus),
        )
    )
    await recompute_scores(session, cfg, referrer_id)


async def get_rank_info(session: AsyncSession, tg_id: int) -> Optional[dict]:
    me = await get_profile(session, tg_id)
    if not me:
        return None

    my_score = float(me.combined_score)
    better = await session.execute(
        select(func.count())
        .select_from(UserProfile)
        .where(
            or_(
                UserProfile.combined_score > my_score,
                and_(UserProfile.combined_score == my_score, UserProfile.tg_id < tg_id),
            )
        )
    )
    better_count = int(better.scalar() or 0)

    total = await session.execute(select(func.count()).select_from(UserProfile))
    total_count = int(total.scalar() or 0)

    return {
        "position": better_count + 1,
        "total": total_count,
        "primary_score": float(me.primary_score),
        "behavior_score": float(me.behavior_score),
        "referral_score": float(me.referral_score),
        "combined_score": float(me.combined_score),
    }


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
