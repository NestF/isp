import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    redis_url: str
    amqp_url: str

    city_bonus: float
    age_weight: float
    rating_weight: float
    age_delta_start: int
    age_delta_step: int
    age_delta_max: int

    rating_initial: float
    like_bonus: float
    dislike_penalty: float
    match_bonus: float
    rating_min_events: int
    top_limit: int
    primary_weight: float
    behavior_weight: float
    referral_weight: float
    cache_ttl_sec: int


def load_config() -> Config:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token or bot_token == "CHANGE_ME":
        raise RuntimeError("BOT_TOKEN не задан. Укажи токен в .env")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL не задан. Укажи строку подключения PostgreSQL в .env")

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        raise RuntimeError("REDIS_URL не задан. Укажи Redis URL в .env")

    amqp_url = os.getenv("AMQP_URL", "").strip()
    if not amqp_url:
        raise RuntimeError("AMQP_URL не задан. Укажи RabbitMQ URL в .env")

    return Config(
        bot_token=bot_token,
        database_url=database_url,
        redis_url=redis_url,
        amqp_url=amqp_url,
        city_bonus=float(os.getenv("CITY_BONUS", "100.0")),
        age_weight=float(os.getenv("AGE_WEIGHT", "50.0")),
        rating_weight=float(os.getenv("RATING_WEIGHT", "0.2")),
        age_delta_start=int(os.getenv("AGE_DELTA_START", "3")),
        age_delta_step=int(os.getenv("AGE_DELTA_STEP", "2")),
        age_delta_max=int(os.getenv("AGE_DELTA_MAX", "10")),
        rating_initial=float(os.getenv("RATING_INITIAL", "1000.0")),
        like_bonus=float(os.getenv("LIKE_BONUS", "8.0")),
        dislike_penalty=float(os.getenv("DISLIKE_PENALTY", "6.0")),
        match_bonus=float(os.getenv("MATCH_BONUS", "40.0")),
        rating_min_events=int(os.getenv("RATING_MIN_EVENTS", "5")),
        top_limit=int(os.getenv("TOP_LIMIT", "10")),
        primary_weight=float(os.getenv("PRIMARY_WEIGHT", "0.45")),
        behavior_weight=float(os.getenv("BEHAVIOR_WEIGHT", "0.45")),
        referral_weight=float(os.getenv("REFERRAL_WEIGHT", "0.10")),
        cache_ttl_sec=int(os.getenv("CACHE_TTL_SEC", "300")),
    )
