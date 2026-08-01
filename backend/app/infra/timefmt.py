"""Single source of truth for formatting event datetimes in user-facing
strings.

Every timestamp in the DB is stored as **naive UTC** (see `EventCreate`
serialisation to `toUtc().toIso8601String()` on the frontend and the SQLAlchemy
`DateTime` columns on the backend). If we call `.strftime()` directly on those
values the resulting string is UTC wall-clock with no timezone label — which
is exactly what caused the "Starts at 11:30" / "Jul 12 · 4:50 PM" mismatch on
the notification card (11:30 UTC == 17:00 IST but the string never said so).

This module funnels every human-facing time render through one converter:

* Naive datetimes are treated as UTC.
* We project into the event's own `Event.timezone` (per-row source of truth)
  if that column is populated; otherwise a demo-wide default read from the
  `FLO_DISPLAY_TZ` env var (falls back to `Asia/Kolkata`).
* The formatted string always ends in a timezone abbreviation (`IST`, `UTC`,
  `PDT`, …) so the reader can never be off by 5.5 hours again.

Only display-side code should call these helpers. SQL-side `strftime()` filters
in `nl2sql.py` operate on the raw UTC column and are intentionally left as-is.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# The demo runs out of India, so IST is the most natural default. Override
# with `FLO_DISPLAY_TZ=America/Los_Angeles` (or any IANA name) if the audience
# is elsewhere. Falls all the way back to UTC if the value is bogus.
_DEFAULT_TZ_NAME = os.environ.get("FLO_DISPLAY_TZ", "Asia/Kolkata")


def _resolve_zone(event_tz: str | None) -> ZoneInfo:
    for candidate in (event_tz, _DEFAULT_TZ_NAME, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            continue
    return ZoneInfo("UTC")


def to_display(dt: datetime, event_tz: str | None = None) -> datetime:
    """Attach UTC (if naive) and project into the chosen display zone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_resolve_zone(event_tz))


def _strip_leading_zero(s: str) -> str:
    """`05:00 PM` → `5:00 PM`, `Jul 05` → `Jul 5`. Idempotent."""
    return s.replace(" 0", " ").replace("  ", " ").strip()


def format_when(dt: datetime | None, event_tz: str | None = None) -> str:
    """`Sat, Jul 12 · 5:00 PM IST` — long form for AI answers / detail lines."""
    if dt is None:
        return "TBD"
    local = to_display(dt, event_tz)
    return _strip_leading_zero(local.strftime("%a, %b %d · %I:%M %p %Z"))


def format_time(dt: datetime | None, event_tz: str | None = None) -> str:
    """`5:00 PM IST` — short form for notifications and inline chips."""
    if dt is None:
        return "TBD"
    local = to_display(dt, event_tz)
    return _strip_leading_zero(local.strftime("%I:%M %p %Z"))


def format_day_time(dt: datetime | None, event_tz: str | None = None) -> str:
    """`Sat 5:00 PM IST` — used by the swipe card `when_where` prompt."""
    if dt is None:
        return "TBD"
    local = to_display(dt, event_tz)
    return _strip_leading_zero(local.strftime("%a %I:%M %p %Z"))
