from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select

from app.domain import matching_service, notification_service, pulse_service
from app.infra.db import SessionLocal
from app.infra.timefmt import format_time
from app.models.event import Event
from app.models.interaction import EventInteraction
from app.models.user import User

logger = logging.getLogger(__name__)


async def beat_pulse_snapshot() -> None:
    try:
        await pulse_service.broadcast_pulse()
    except Exception as exc:
        logger.warning("pulse beat failed: %s", exc)


def beat_event_starting_soon() -> None:
    """Differentiated pre-event notifier.

    The three flavours of event intent (`rsvp`, `save`, `like`) get very
    different treatment here — a deliberate product choice so users have a
    real reason to pick one over another instead of "which button do I
    press for this thing I care about?".

    * `rsvp` (hard commitment): fires TWO notifications per event —
      a 30-minute heads-up ("Get ready...") and a 10-minute call to arms
      ("Starting soon..."). This models the RSVP as an obligation.
    * `save` (soft shortlist): fires ONE notification, 10 minutes out,
      framed as a nudge ("Still want to catch...?"). Only users who did
      NOT also RSVP get this — RSVPs get the firmer wording instead.
    * `like` (implicit taste signal from the swipe deck): fires nothing.
      It's a personalization fingerprint, not a user-managed shortlist.

    De-duped per (event, window, start_time) with an in-memory set that
    resets every process boot — the notification table is still the
    source of truth for anything the user has already seen.
    """
    db = SessionLocal()
    try:
        now = datetime.utcnow()

        # --- 30-minute heads-up window (RSVP only) ------------------------
        heads_start = now + timedelta(minutes=10)
        heads_end = now + timedelta(minutes=30)
        heads_events = list(
            db.execute(
                select(Event).where(
                    Event.start_time >= heads_start,
                    Event.start_time <= heads_end,
                )
            ).scalars().all()
        )
        for ev in heads_events:
            key = f"event_soon:rsvp30:{ev.id}:{ev.start_time.isoformat()}"
            if key in _fired:
                continue
            _fired.add(key)
            rsvp_uids = _users_with_type(db, ev.id, "rsvp")
            for uid in rsvp_uids:
                _safe_push(
                    db,
                    user_id=uid,
                    type_="event_starting_soon",
                    title=f"Get ready: {ev.title}",
                    body=f"Starts at {format_time(ev.start_time, ev.timezone)} — ~30 min from now.",
                    deep_link=f"/events/{ev.id}",
                )

        # --- 10-minute alarm window (RSVP + save-only) --------------------
        alarm_events = list(
            db.execute(
                select(Event).where(
                    Event.start_time >= now,
                    Event.start_time <= now + timedelta(minutes=10),
                )
            ).scalars().all()
        )
        for ev in alarm_events:
            rsvp_uids = set(_users_with_type(db, ev.id, "rsvp"))
            save_uids = set(_users_with_type(db, ev.id, "save"))
            # Save-only means the user showed soft intent but never
            # committed — give them the gentler prompt.
            save_only = save_uids - rsvp_uids

            rsvp_key = f"event_soon:rsvp10:{ev.id}:{ev.start_time.isoformat()}"
            if rsvp_key not in _fired:
                _fired.add(rsvp_key)
                for uid in rsvp_uids:
                    _safe_push(
                        db,
                        user_id=uid,
                        type_="event_starting_soon",
                        title=f"Starting soon: {ev.title}",
                        body=f"Starts at {format_time(ev.start_time, ev.timezone)}. See you there.",
                        deep_link=f"/events/{ev.id}",
                    )

            save_key = f"event_soon:save10:{ev.id}:{ev.start_time.isoformat()}"
            if save_key not in _fired:
                _fired.add(save_key)
                for uid in save_only:
                    _safe_push(
                        db,
                        user_id=uid,
                        type_="event_saved_reminder",
                        title=f"Still want to catch {ev.title}?",
                        body=f"Starts at {format_time(ev.start_time, ev.timezone)} — you saved it earlier.",
                        deep_link=f"/events/{ev.id}",
                    )
    finally:
        db.close()


def _users_with_type(db, event_id: int, type_: str) -> list[int]:
    return [
        int(uid)
        for uid in db.execute(
            select(EventInteraction.user_id).where(
                EventInteraction.event_id == event_id,
                EventInteraction.type == type_,
            )
        )
        .scalars()
        .unique()
        .all()
    ]


def _safe_push(db, **kwargs) -> None:
    try:
        notification_service.push(db, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("notification push failed: %s", exc)


def beat_nightly_matches() -> None:
    db = SessionLocal()
    try:
        uids = db.execute(select(User.id).where(User.opt_in_networking.is_(True))).scalars().all()
        for uid in uids:
            try:
                matching_service.recommend_people(db, user_id=int(uid), k=20)
            except Exception as exc:
                logger.warning("nightly matches for %s failed: %s", uid, exc)
    finally:
        db.close()


_fired: set[str] = set()
