"""Refresh demo assets: speaker headshots, event covers, user avatars, reels.

This is a one-shot maintenance script for the demo dataset. It is designed to
be *additive to* — and safely re-runnable from — the normal boot-time
`app.scripts.seed` flow. Each step is guarded by a CLI flag so container boot
never accidentally touches assets.

Usage (from the ``backend/`` directory)::

    uv run python -m app.scripts.seed_assets --all
    uv run python -m app.scripts.seed_assets --refresh-headshots
    uv run python -m app.scripts.seed_assets --refresh-covers
    uv run python -m app.scripts.seed_assets --reset-user-avatars
    uv run python -m app.scripts.seed_assets --reset-reels

Referential-integrity notes
---------------------------
* ``refresh_speaker_headshots`` / ``refresh_event_covers`` only ``UPDATE`` a
  single column per row — every other field, FK, timestamp, and join row
  stays untouched.
* ``nullify_user_avatars`` only touches ``user.avatar_url``.
* ``reseed_reels`` deletes rows from ``reel_interaction`` and ``reel`` in
  that order (interactions first to make the intent explicit; the FK cascade
  would also do it) inside a single transaction, then re-inserts fresh
  ``Reel`` rows. Nothing else references ``reel.id`` in this schema, so no
  other tables need to change.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

try:
    import imageio_ffmpeg
except ImportError:  # pragma: no cover
    imageio_ffmpeg = None  # type: ignore[assignment]

from app.infra.blob import blob_store
from app.infra.db import SessionLocal, ensure_schema
from app.models.event import Event, Speaker
from app.models.reel import Reel, ReelInteraction
from app.models.user import User

logger = logging.getLogger(__name__)

# URLs baked into the DB are signed with a 10-year TTL so they behave like
# permanent links in demo/dev without changing the media routing layer.
STATIC_URL_TTL = 60 * 60 * 24 * 365 * 10

# `speaker.headshot_url` / `event.cover_image_url` are consumed directly by
# `Image.network(...)` in the Flutter web app, which resolves relative paths
# against the frontend origin (localhost:3000) — so we bake an absolute URL
# into the DB. `PUBLIC_API_BASE_URL` overrides the default for non-local runs.
PUBLIC_API_BASE_URL = os.environ.get("PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")


def _absolute_media_url(key: str) -> str:
    return f"{PUBLIC_API_BASE_URL}{blob_store.signed_url(key, ttl_seconds=STATIC_URL_TTL)}"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "-", s) or "x"


def _pick_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "arialbd.ttf" if bold else "arial.ttf",
        "seguibl.ttf" if bold else "segoeui.ttf",
        "Segoe UI.ttf",
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "Helvetica.ttc",
    ]
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _save_jpeg(img: Image.Image, dst: Path, max_side: int = 512, quality: int = 88) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_side:
        if w >= h:
            new_w, new_h = max_side, int(h * max_side / w)
        else:
            new_h, new_w = max_side, int(w * max_side / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
    img.save(dst, format="JPEG", quality=quality, optimize=True)


# ---------------------------------------------------------------------------
# Speaker headshots
# ---------------------------------------------------------------------------

_WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{name}"
_WIKI_API = "https://en.wikipedia.org/w/api.php"
_UA = {"User-Agent": "eventive-seed-assets/1.0 (local demo seeding; contact: dev@eventive.local)"}

# Wikipedia's exact-title lookup misses many well-known people (disambiguation
# pages, alternative spellings, wrong "Jeremy Howard"). This override table
# points at the correct Wikipedia article slug for the ones we care about so
# their real photos win over the initials fallback.
_WIKI_TITLE_OVERRIDES: dict[str, str] = {
    "Demis Hassabis": "Demis_Hassabis",
    "Jeremy Howard": "Jeremy_Howard_(entrepreneur)",
    "Sebastian Raschka": "Sebastian_Raschka",
    "Percy Liang": "Percy_Liang",
    "Chip Huyen": "Chip_Huyen",
    "Aravind Srinivas": "Aravind_Srinivas",
    "Harrison Chase": "Harrison_Chase",
    "Clement Delangue": "Clément_Delangue",
    "Sara Hooker": "Sara_Hooker",
    "Rachel Thomas": "Rachel_Thomas_(academic)",
    "Jerry Liu": "Jerry_Liu_(entrepreneur)",
}


def _download(url: str, timeout: float = 15.0) -> bytes | None:
    try:
        r = requests.get(url, timeout=timeout, headers=_UA)
    except Exception as exc:
        logger.debug("download failed %s: %s", url, exc)
        return None
    if r.status_code != 200 or not r.content:
        return None
    return r.content


def _validate_image_bytes(data: bytes) -> Image.Image | None:
    # 5 KB — 10 MB. Some Wikipedia originals are large; we resize on save anyway.
    if len(data) < 5_000 or len(data) > 10_000_000:
        return None
    try:
        Image.open(io.BytesIO(data)).verify()
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return None
    if img.width < 200 or img.height < 200:
        return None
    ratio = img.width / img.height
    # Reject only extreme banners / super-tall panels; allow most portraits + group photos.
    if ratio < 0.35 or ratio > 2.6:
        return None
    return img


def _wiki_summary_image(title: str) -> str | None:
    """Return the highest-quality image URL from the REST summary endpoint."""
    encoded = requests.utils.quote(title)
    try:
        r = requests.get(_WIKI_SUMMARY.format(name=encoded), timeout=15.0, headers=_UA)
        if r.status_code != 200:
            return None
        payload = r.json()
    except Exception:
        return None
    # Ignore disambiguation stubs — they carry misleading images.
    if payload.get("type") == "disambiguation":
        return None
    for section in ("originalimage", "thumbnail"):
        blob = payload.get(section)
        if isinstance(blob, dict) and blob.get("source"):
            return blob["source"]
    return None


def _wiki_pageimage(title: str) -> str | None:
    """MediaWiki `prop=pageimages` fetches the article's designated lead image."""
    try:
        r = requests.get(
            _WIKI_API,
            timeout=15.0,
            headers=_UA,
            params={
                "action": "query",
                "titles": title,
                "prop": "pageimages",
                "pithumbsize": "1024",
                "format": "json",
                "redirects": "1",
            },
        )
        if r.status_code != 200:
            return None
        pages = r.json().get("query", {}).get("pages", {}) or {}
    except Exception:
        return None
    for page in pages.values():
        thumb = page.get("thumbnail") or {}
        src = thumb.get("source")
        if src:
            return src
    return None


def _wiki_search_title(query: str) -> str | None:
    """First-hit title from MediaWiki full-text search."""
    try:
        r = requests.get(
            _WIKI_API,
            timeout=15.0,
            headers=_UA,
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
            },
        )
        if r.status_code != 200:
            return None
        hits = r.json().get("query", {}).get("search", []) or []
    except Exception:
        return None
    for hit in hits:
        title = hit.get("title")
        if title:
            return title
    return None


def _fetch_wikipedia_image(name: str) -> tuple[bytes, str] | None:
    """Try, in order: manual override → summary API → pageimages API → search-then-summary."""
    candidate_titles: list[str] = []
    override = _WIKI_TITLE_OVERRIDES.get(name)
    if override:
        candidate_titles.append(override)
    candidate_titles.append(name.replace(" ", "_"))

    src: str | None = None
    for title in candidate_titles:
        src = _wiki_summary_image(title) or _wiki_pageimage(title)
        if src:
            break

    if not src:
        # Last resort — search-then-summary. Disambiguates unusual names.
        found = _wiki_search_title(name)
        if found:
            src = _wiki_summary_image(found) or _wiki_pageimage(found)

    if not src:
        return None
    data = _download(src)
    if not data:
        return None
    return data, src


def _initials_from(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _initials_image(name: str, size: int = 512) -> Image.Image:
    letters = _initials_from(name)
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    # Deterministic but not too dark background.
    r = 60 + (int(h[0:2], 16) % 140)
    g = 60 + (int(h[2:4], 16) % 140)
    b = 60 + (int(h[4:6], 16) % 140)
    img = Image.new("RGB", (size, size), (r, g, b))
    draw = ImageDraw.Draw(img)
    font = _pick_font(int(size * 0.42), bold=True)
    bbox = draw.textbbox((0, 0), letters, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(
        ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1]),
        letters,
        fill=(255, 255, 255),
        font=font,
    )
    return img


def refresh_speaker_headshots(db: Session, force: bool = False) -> dict[str, Any]:
    manifest: list[dict[str, Any]] = []
    counts = {"wikipedia": 0, "initials_fallback": 0, "skipped_existing": 0}
    speakers = list(db.execute(select(Speaker).order_by(Speaker.id)).scalars().all())
    for sp in speakers:
        if sp.headshot_url and not force:
            counts["skipped_existing"] += 1
            manifest.append(
                {"speaker_id": sp.id, "name": sp.name, "source": "existing", "url": sp.headshot_url}
            )
            continue
        slug = _slugify(sp.name)
        key = f"speakers/{slug}.jpg"
        dst = blob_store.path_for(key)
        source = "initials_fallback"
        source_url = None
        wiki = _fetch_wikipedia_image(sp.name)
        if wiki is not None:
            data, src_url = wiki
            img = _validate_image_bytes(data)
            if img is not None:
                _save_jpeg(img, dst)
                source = "wikipedia"
                source_url = src_url
        if source == "initials_fallback":
            _save_jpeg(_initials_image(sp.name), dst)
        sp.headshot_url = _absolute_media_url(key)
        counts[source] += 1
        manifest.append(
            {
                "speaker_id": sp.id,
                "name": sp.name,
                "source": source,
                "source_url": source_url,
                "key": key,
            }
        )
        logger.info("speaker %-24s -> %s", sp.name, source)
    db.commit()
    manifest_path = blob_store.path_for("speakers/_manifest.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"counts": counts, "manifest_path": str(manifest_path)}


# ---------------------------------------------------------------------------
# Event cover images (Pillow, offline, deterministic)
# ---------------------------------------------------------------------------

TRACK_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "AI":              ((79, 70, 229),  (147, 51, 234)),   # indigo -> purple
    "Infra":           ((30, 41, 59),   (37, 99, 235)),    # slate  -> blue
    "AI Safety":       ((220, 38, 38),  (234, 88, 12)),    # red    -> orange
    "Startups":        ((16, 185, 129), (13, 148, 136)),   # green  -> teal
    "Data":            ((245, 158, 11), (217, 119, 6)),    # amber
    "Edge":            ((99, 102, 241), (14, 165, 233)),   # indigo -> sky
    "Healthcare AI":   ((236, 72, 153), (168, 85, 247)),   # pink   -> violet
    "Robotics":        ((217, 70, 239), (79, 70, 229)),    # fuchsia -> indigo
    "Climate Tech":    ((5, 150, 105),  (16, 185, 129)),   # emerald
    "Fintech":         ((59, 130, 246), (14, 116, 144)),   # blue   -> cyan
    "Frontend":        ((244, 114, 182),(168, 85, 247)),   # pink   -> violet
    "Developer Tools": ((6, 182, 212),  (99, 102, 241)),   # cyan   -> indigo
    "Education":       ((251, 191, 36), (245, 101, 101)),  # amber  -> red
}
_DEFAULT_PALETTE = ((55, 65, 81), (17, 24, 39))  # gray -> near-black


def _wrap_title(title: str, per_line: int = 14) -> list[str]:
    return textwrap.wrap(title, width=per_line) or [title]


def _mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


def _lighten(c: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    """Blend colour ``c`` toward white by ``t`` (0..1)."""
    return (
        min(255, int(c[0] + (255 - c[0]) * t)),
        min(255, int(c[1] + (255 - c[1]) * t)),
        min(255, int(c[2] + (255 - c[2]) * t)),
    )


def _make_cover(title: str, track: str | None, subtitle: str | None, seed_key: str = "") -> Image.Image:
    """Portrait 9:16 event *wallpaper*.

    ``EventCardWidget`` in Flutter already paints:
      • its own **track badge** at top-left (y ≈ 110)
      • a **status pill** at top-right (y ≈ 110)
      • the **event title / tags / CTA button / action bar** in the bottom
        third
      • a top→bottom dark gradient at stops 0.20 / 0.50 / 1.0 (transparent →
        30 % black → 85 % black)

    List rows render the same image cropped to a 68×68 square from the
    vertical centre. So the image must:
      • carry **no text or badge** (they collide with the app UI on the big
        card and are unreadable on the thumbnail)
      • put its **visual focus in the middle** so the thumb crop still looks
        good
      • stay **bright at the bottom** so the app's 85 % dark overlay leaves a
        visible colour tint instead of pure black in the corners
      • **vary per event** so cards don't all look identical
    """
    W, H = 1080, 1920  # 9:16, mobile-friendly
    c1, c2 = TRACK_PALETTES.get((track or "").strip(), _DEFAULT_PALETTE)

    # Deterministic per-event randomness — makes each card feel unique
    # without introducing non-reproducible output between seed runs.
    h = hashlib.md5((seed_key or title).encode("utf-8")).digest()

    # Brighter tint at the very bottom so the app's 85 % dark overlay still
    # renders as colour, not pure black. We interpolate along a 3-stop path:
    # c1 (top) → c1_bright (upper middle) → c2 (mid) → c2_bright (bottom).
    c1_bright = _lighten(c1, 0.20)
    c2_bright = _lighten(c2, 0.30)
    stops = [(0.00, c1), (0.35, c1_bright), (0.65, c2), (1.00, c2_bright)]

    def _color_at(t: float) -> tuple[int, int, int]:
        for i in range(len(stops) - 1):
            s0, ca = stops[i]
            s1, cb = stops[i + 1]
            if t <= s1:
                span = max(s1 - s0, 1e-6)
                local = (t - s0) / span
                return _mix(ca, cb, local)
        return stops[-1][1]

    img = Image.new("RGB", (W, H), c1)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        draw.line([(0, y), (W, y)], fill=_color_at(y / (H - 1)))

    # ------------------------------------------------------------------
    # Decorative orbs — all *bright* (no dark accents that would deepen
    # the app's shadow into pure black in the bottom corners). Positions
    # jittered by the per-event hash so no two cards look identical.
    # ------------------------------------------------------------------
    highlight = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    hl_draw = ImageDraw.Draw(highlight)

    def _orb(cx: int, cy: int, radius: int, tint: tuple[int, int, int], strength: int) -> None:
        """Layered soft orb (approximates a Gaussian glow with a handful of ellipses)."""
        # 5 concentric ellipses, alpha decays outward.
        for i, (r_mul, a_mul) in enumerate(((1.00, 0.35), (0.75, 0.55), (0.55, 0.75), (0.35, 0.90), (0.18, 1.00))):
            r = int(radius * r_mul)
            a = int(strength * a_mul)
            hl_draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(tint[0], tint[1], tint[2], a))

    # Jitter each orb's placement in a bounded region using bytes from the hash.
    def _jitter(base_x: int, base_y: int, spread: int, idx: int) -> tuple[int, int]:
        jx = (h[(idx * 2) % 16] - 128) * spread // 128
        jy = (h[(idx * 2 + 1) % 16] - 128) * spread // 128
        return base_x + jx, base_y + jy

    # 1) A large soft glow near the vertical centre — this is what the
    #    68×68 thumbnail crop primarily samples, so make it the hero.
    cx, cy = _jitter(W // 2, H // 2, spread=180, idx=0)
    _orb(cx, cy, radius=620, tint=(255, 255, 255), strength=52)

    # 2) A secondary accent orb — tinted with the *complementary* end of the
    #    palette so the centre has depth rather than a flat white haze.
    cx2, cy2 = _jitter(int(W * 0.68), int(H * 0.42), spread=140, idx=1)
    _orb(cx2, cy2, radius=440, tint=_lighten(c2, 0.55), strength=70)

    # 3) Top-right glow — feels premium, and is behind the app's status pill
    #    so it never competes with UI.
    cx3, cy3 = _jitter(int(W * 0.85), int(H * 0.14), spread=80, idx=2)
    _orb(cx3, cy3, radius=360, tint=(255, 255, 255), strength=40)

    # 4) Bottom-left glow — critical: prevents the "black corner" look
    #    after the 85 % dark overlay hits. Skew the tint toward warm/bright.
    cx4, cy4 = _jitter(int(W * 0.12), int(H * 0.88), spread=80, idx=3)
    _orb(cx4, cy4, radius=420, tint=_lighten(c1, 0.65), strength=90)

    # 5) Bottom-right glow — symmetric with (4). Same purpose.
    cx5, cy5 = _jitter(int(W * 0.88), int(H * 0.88), spread=80, idx=4)
    _orb(cx5, cy5, radius=420, tint=_lighten(c2, 0.65), strength=90)

    img.paste(highlight, (0, 0), highlight)

    # Explicitly no text: no title, no subtitle, no badge, no wordmark.
    # The Flutter card overlays render all of that from the event fields.
    _ = title, subtitle  # silence linters — kept in the signature for API stability.

    return img


def _subtitle_for(event: Event) -> str | None:
    for candidate in (event.abstract, event.description):
        if candidate and candidate.strip():
            return candidate.strip()
    return None


def refresh_event_covers(db: Session, force: bool = False) -> dict[str, Any]:
    counts = {"generated": 0, "skipped_existing": 0}
    events = list(db.execute(select(Event).order_by(Event.id)).scalars().all())
    for ev in events:
        if ev.cover_image_url and not force:
            counts["skipped_existing"] += 1
            continue
        ext_id = (ev.external_id or f"event-{ev.id}").strip() or f"event-{ev.id}"
        slug = _slugify(ext_id)
        key = f"events/{slug}.jpg"
        dst = blob_store.path_for(key)
        img = _make_cover(ev.title, ev.track, _subtitle_for(ev), seed_key=ext_id)
        _save_jpeg(img, dst, max_side=1920, quality=85)
        ev.cover_image_url = _absolute_media_url(key)
        counts["generated"] += 1
        logger.info("cover %s -> %s", ext_id, key)
    db.commit()
    return {"counts": counts}


# ---------------------------------------------------------------------------
# User avatars → NULL (frontend has its own initials fallback)
# ---------------------------------------------------------------------------


def nullify_user_avatars(db: Session) -> dict[str, int]:
    stmt = update(User).where(User.avatar_url.is_not(None)).values(avatar_url=None)
    result = db.execute(stmt)
    db.commit()
    return {"nulled": int(result.rowcount or 0)}


# ---------------------------------------------------------------------------
# Reels: transcode + thumbnail + reseed
# ---------------------------------------------------------------------------


def _ffmpeg_exe() -> str:
    if imageio_ffmpeg is None:
        raise RuntimeError("imageio-ffmpeg is not installed — cannot transcode reels")
    return imageio_ffmpeg.get_ffmpeg_exe()


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")


def _probe_duration_seconds(path: Path) -> float | None:
    result = subprocess.run(
        [_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    match = _DURATION_RE.search(result.stderr)
    if not match:
        return None
    h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
    return h * 3600 + m * 60 + s


def _transcode_reel(src: Path, dst: Path, max_duration: float = 60.0) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-t",
        str(max_duration),
        "-vf",
        (
            "scale='if(gt(a,720/1280),720,-2)':'if(gt(a,720/1280),-2,1280)':"
            "force_original_aspect_ratio=decrease,"
            "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black"
        ),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg transcode failed for {src.name}: {result.stderr.strip()[-800:]}"
        )


def _extract_thumbnail(src: Path, dst: Path, at_seconds: float = 0.5) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(at_seconds),
        "-i",
        str(src),
        "-vframes",
        "1",
        "-vf",
        "scale=480:854:force_original_aspect_ratio=decrease",
        "-q:v",
        "5",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg thumbnail failed for {src.name}: {result.stderr.strip()[-800:]}"
        )


_REEL_CAPTIONS = [
    "Kicking off day one at Eventive",
    "Backstage energy is unreal",
    "Between sessions vibes",
    "That moment when RAG finally clicks",
    "Speaker room whispers",
    "Networking floor is buzzing",
    "Live demo from the main stage",
    "Queue for the AI Safety panel",
    "Wrapping up an incredible day",
]


def reseed_reels(db: Session, src_dir: Path) -> dict[str, Any]:
    if not src_dir.is_dir():
        raise FileNotFoundError(f"reel source folder not found: {src_dir}")
    admin = db.execute(select(User).where(User.is_admin.is_(True)).limit(1)).scalar_one_or_none()
    if admin is None:
        raise RuntimeError("no admin user found — cannot own the seeded reels")

    old_reels = list(db.execute(select(Reel)).scalars().all())
    old_keys: list[str] = []
    for r in old_reels:
        if r.storage_key:
            old_keys.append(r.storage_key)
        if r.thumbnail_key:
            old_keys.append(r.thumbnail_key)

    interactions_deleted = db.execute(delete(ReelInteraction)).rowcount
    reels_deleted = db.execute(delete(Reel)).rowcount
    db.commit()

    for k in old_keys:
        try:
            blob_store.delete(k)
        except Exception as exc:
            logger.debug("failed to delete blob %s: %s", k, exc)

    reels_root = blob_store.path_for("reels")
    if reels_root.is_dir():
        for f in reels_root.iterdir():
            if not f.is_file():
                continue
            name = f.name
            if (
                name.startswith("seed_")
                or name.startswith("raw_")
                or name in {"expired.mp4", "m.mp4", "media_test.mp4"}
                or re.match(r"^\d+\.(mp4|jpg|jpeg|png)$", name)
            ):
                try:
                    f.unlink()
                except Exception as exc:
                    logger.debug("failed to unlink stale reel file %s: %s", f, exc)

    videos = sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".mp4")
    added: list[dict[str, Any]] = []
    for i, src in enumerate(videos, start=1):
        video_key = f"reels/seed_{i:02d}.mp4"
        thumb_key = f"reels/seed_{i:02d}.jpg"
        video_dst = blob_store.path_for(video_key)
        thumb_dst = blob_store.path_for(thumb_key)
        logger.info("transcoding %s -> %s", src.name, video_key)
        _transcode_reel(src, video_dst)
        _extract_thumbnail(video_dst, thumb_dst)
        duration = _probe_duration_seconds(video_dst)
        if duration is not None and duration > 60.5:
            duration = 60.0
        caption = _REEL_CAPTIONS[(i - 1) % len(_REEL_CAPTIONS)]
        reel = Reel(
            user_id=admin.id,
            caption=caption,
            storage_key=video_key,
            thumbnail_key=thumb_key,
            duration_seconds=duration,
            status="ready",
            video_url=blob_store.signed_url(video_key, ttl_seconds=STATIC_URL_TTL),
            thumbnail_url=blob_store.signed_url(thumb_key, ttl_seconds=STATIC_URL_TTL),
        )
        db.add(reel)
        db.flush()
        added.append(
            {
                "id": reel.id,
                "src": src.name,
                "video_key": video_key,
                "thumb_key": thumb_key,
                "duration_s": duration,
                "size_bytes": video_dst.stat().st_size if video_dst.exists() else None,
            }
        )
    db.commit()
    return {
        "deleted_reels": int(reels_deleted or 0),
        "deleted_interactions": int(interactions_deleted or 0),
        "added": added,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument("--all", action="store_true", help="run every step")
    parser.add_argument("--refresh-headshots", action="store_true")
    parser.add_argument("--refresh-covers", action="store_true")
    parser.add_argument("--reset-user-avatars", action="store_true")
    parser.add_argument("--reset-reels", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite existing values for headshots / covers (default: skip populated rows)",
    )
    parser.add_argument(
        "--reels-src",
        type=Path,
        default=Path("data/7180175-hd_1080_1920_25fps"),
        help="folder holding raw .mp4 sources for --reset-reels",
    )
    args = parser.parse_args()

    if args.all:
        args.refresh_headshots = True
        args.refresh_covers = True
        args.reset_user_avatars = True
        args.reset_reels = True

    if not any(
        [
            args.refresh_headshots,
            args.refresh_covers,
            args.reset_user_avatars,
            args.reset_reels,
        ]
    ):
        parser.error("nothing to do — pass at least one --refresh-* / --reset-* flag or --all")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ensure_schema()

    report: dict[str, Any] = {}
    db: Session = SessionLocal()
    try:
        if args.refresh_headshots:
            report["headshots"] = refresh_speaker_headshots(db, force=args.force)
        if args.refresh_covers:
            report["covers"] = refresh_event_covers(db, force=args.force)
        if args.reset_user_avatars:
            report["user_avatars"] = nullify_user_avatars(db)
        if args.reset_reels:
            report["reels"] = reseed_reels(db, args.reels_src)
    finally:
        db.close()

    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
