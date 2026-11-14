"""Celery worker + beat (alternative to BACKGROUND_JOBS=true).
Run: celery -A app.worker.celery worker -B -l info
"""
from celery import Celery

from . import jobs
from .config import settings

celery = Celery("assistant", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.timezone = "Asia/Kolkata"
celery.conf.beat_schedule = {
    "reminders": {"task": "app.worker.send_reminders", "schedule": 60.0},
    "gmail": {"task": "app.worker.sync_gmail", "schedule": 600.0},
    "calendar": {"task": "app.worker.pull_calendars", "schedule": 600.0},
    "followups": {"task": "app.worker.followup_cycle", "schedule": 3 * 3600.0},
}


@celery.task(name="app.worker.send_reminders")
def send_reminders() -> dict:
    return jobs.send_reminders()


@celery.task(name="app.worker.sync_gmail")
def sync_gmail() -> dict:
    return jobs.sync_gmail_all()


@celery.task(name="app.worker.pull_calendars")
def pull_calendars() -> dict:
    return jobs.pull_calendars()


@celery.task(name="app.worker.followup_cycle")
def followup_cycle() -> dict:
    return jobs.followup_cycle()
