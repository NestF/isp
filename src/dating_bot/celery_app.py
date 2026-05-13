import os

from celery import Celery


def make_celery() -> Celery:
    broker_url = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672//")
    backend_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

    app = Celery("dating_bot", broker=broker_url, backend=backend_url, include=["dating_bot.tasks"])
    app.conf.timezone = "UTC"
    app.conf.broker_connection_retry_on_startup = True
    app.conf.task_acks_late = True
    app.conf.worker_prefetch_multiplier = 1
    app.conf.beat_schedule = {
        "recompute_ratings": {
            "task": "dating_bot.tasks.recompute_all_ratings",
            "schedule": int(os.getenv("RATING_RECOMPUTE_SEC", "300")),
        }
    }
    return app


celery_app = make_celery()

