from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserProfile(Base):
    __tablename__ = "user_profiles"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    interests: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    pref_age_min: Mapped[int] = mapped_column(Integer, nullable=False, default=18)
    pref_age_max: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    pref_gender: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    pref_city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    media: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    primary_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    behavior_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    referral_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rating_score: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    likes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dislikes_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matches_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dialogs_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    referrals_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


Index("ix_profiles_city", UserProfile.city)
Index("ix_profiles_age", UserProfile.age)
Index("ix_profiles_rating", UserProfile.rating_score)


class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("viewer_id", "target_id", name="uq_votes_viewer_target"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    viewer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_profiles.tg_id", ondelete="CASCADE"), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_profiles.tg_id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index("ix_votes_viewer", Vote.viewer_id)
Index("ix_votes_target", Vote.target_id)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("user1_id", "user2_id", name="uq_match_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user1_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_profiles.tg_id", ondelete="CASCADE"), nullable=False
    )
    user2_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_profiles.tg_id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index("ix_matches_u1", Match.user1_id)
Index("ix_matches_u2", Match.user2_id)


class ProfileRating(Base):
    __tablename__ = "profile_ratings"

    tg_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("user_profiles.tg_id", ondelete="CASCADE"), primary_key=True
    )
    primary_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    behavior_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    referral_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    combined_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class InteractionEvent(Base):
    __tablename__ = "interaction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


Index("ix_events_type", InteractionEvent.event_type)
Index("ix_events_created_at", InteractionEvent.created_at)
