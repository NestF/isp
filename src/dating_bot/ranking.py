from __future__ import annotations

from datetime import datetime

from dating_bot.config import Config


def compute_primary_score(profile: dict, cfg: Config) -> float:
    score = 0.0

    age = int(profile.get("age") or 0)
    if 18 <= age <= 100:
        score += 10.0

    gender = profile.get("gender")
    if gender:
        score += 5.0

    city = profile.get("city")
    if city:
        score += 10.0

    interests = profile.get("interests") or []
    score += min(10.0, float(len(interests)) * 2.0)

    bio = (profile.get("bio") or "").strip()
    if bio:
        score += 10.0

    photos = profile.get("media") or []
    score += min(15.0, float(len(photos)) * 5.0)

    pref_age_min = int(profile.get("pref_age_min") or 18)
    pref_age_max = int(profile.get("pref_age_max") or 100)
    if 18 <= pref_age_min <= pref_age_max <= 100:
        score += 10.0

    if profile.get("pref_city"):
        score += 5.0
    if profile.get("pref_gender"):
        score += 5.0

    return score


def compute_behavior_score(profile: dict, now: datetime | None = None) -> float:
    likes = int(profile.get("likes_count") or 0)
    dislikes = int(profile.get("dislikes_count") or 0)
    matches = int(profile.get("matches_count") or 0)
    dialogs = int(profile.get("dialogs_count") or 0)

    total = likes + dislikes
    like_ratio = (likes / total) if total > 0 else 0.0

    score = 0.0
    score += min(50.0, likes * 1.0)
    score += like_ratio * 30.0
    score += min(40.0, matches * 5.0)
    score += min(30.0, dialogs * 10.0)

    if now:
        hour = now.hour
        if 18 <= hour <= 23:
            score += 5.0
        elif 0 <= hour <= 3:
            score += 2.0

    return score


def compute_combined_score(profile: dict, cfg: Config) -> float:
    primary = float(profile.get("primary_score") or 0.0)
    behavior = float(profile.get("behavior_score") or 0.0)
    referral = float(profile.get("referral_score") or 0.0)
    return primary * cfg.primary_weight + behavior * cfg.behavior_weight + referral * cfg.referral_weight
