import logging
import os
import sys
import threading
import time

logger = logging.getLogger(__name__)

_poller_started = False
_poller_lock = threading.Lock()


def _should_skip_autostart() -> bool:
    """Don't start the poller during migrate, tests, shell, etc."""
    skip_commands = {
        "migrate",
        "makemigrations",
        "collectstatic",
        "shell",
        "test",
        "createsuperuser",
        "seed_currencies",
    }
    if any(cmd in sys.argv for cmd in skip_commands):
        return True

    # Django runserver spawns a reloader parent; only start in the child.
    if "runserver" in sys.argv and os.environ.get("RUN_MAIN") != "true":
        return True

    return False


def _poll_loop(interval_seconds: int):
    from .email_fetch_runner import run_email_fetch_once

    logger.info(
        "IMAP email poller started (every %s seconds).",
        interval_seconds,
    )

    # Small delay so the web process finishes booting first.
    time.sleep(5)

    auth_backoff_seconds = 15 * 60

    while True:
        sleep_for = max(15, interval_seconds)
        try:
            result = run_email_fetch_once()
            if result.get("skipped"):
                logger.debug("IMAP poll skipped: %s", result.get("reason"))
            elif result.get("auth_failed"):
                logger.error(
                    "IMAP authentication failed. Pausing poller for %s seconds. "
                    "Fix IMAP_EMAIL / IMAP_PASSWORD / IMAP_HOST on Render.",
                    auth_backoff_seconds,
                )
                sleep_for = auth_backoff_seconds
            elif not result.get("success"):
                logger.warning("IMAP poll failed: %s", result.get("error"))
            elif result.get("count"):
                logger.info(
                    "IMAP poll processed %s email(s).",
                    result.get("count"),
                )
        except Exception:
            logger.exception("Unexpected IMAP poller error.")

        time.sleep(sleep_for)


def start_imap_poller_if_enabled():
    """
    Start a daemon thread that polls IMAP for receipt emails.

    Designed for free hosts (e.g. Render web-only) where Celery worker/beat
    are not available. Enable with EMAIL_IMAP_POLL_ENABLED=True and IMAP_*.
    """
    global _poller_started

    from django.conf import settings

    if not getattr(settings, "EMAIL_IMAP_POLL_ENABLED", False):
        return

    if _should_skip_autostart():
        return

    if not (
        getattr(settings, "IMAP_HOST", None)
        and getattr(settings, "IMAP_EMAIL", None)
        and getattr(settings, "IMAP_PASSWORD", None)
    ):
        logger.warning(
            "EMAIL_IMAP_POLL_ENABLED is True but IMAP_HOST/EMAIL/PASSWORD "
            "are incomplete; poller not started."
        )
        return

    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True

    interval = int(getattr(settings, "EMAIL_IMAP_POLL_INTERVAL_SECONDS", 30) or 30)

    thread = threading.Thread(
        target=_poll_loop,
        args=(interval,),
        name="zepex-imap-poller",
        daemon=True,
    )
    thread.start()
