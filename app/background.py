"""In-process scheduler. Enable with BACKGROUND_JOBS=true. No Redis or Celery needed (good for local use)."""
import asyncio
import logging

from . import jobs

log = logging.getLogger("background")


async def _run(fn) -> None:
    try:
        await asyncio.to_thread(fn)
    except Exception:  # one failing job must never stop the loop
        log.exception("background job %s failed", fn.__name__)


async def run(interval_minutes: int = 10) -> None:
    interval = max(1, interval_minutes)
    await asyncio.sleep(20)  # let the server finish starting
    tick = 0
    while True:
        await _run(jobs.send_reminders)                         # every minute
        if tick % interval == 0:
            await _run(jobs.sync_gmail_all)                     # every N minutes
            await _run(jobs.pull_calendars)
        if tick % (interval * 18) == 0:
            await _run(jobs.followup_cycle)                     # about every 3 hours at the default
        tick += 1
        await asyncio.sleep(60)
