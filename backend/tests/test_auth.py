"""E2E tests for Phase 14 auth: register / login / refresh / logout / me."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("LLM_PROVIDER", "stub")


def _bootstrap_isolated_db() -> None:
    tmp = tempfile.mkdtemp(prefix="eventive_auth_test_")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/eventive.db"
    os.environ["DATA_DIR"] = tmp
    os.environ["SEED_DEMO_FIXTURES"] = "false"


_bootstrap_isolated_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.infra.config import get_settings  # noqa: E402
from app.infra.db import ensure_schema, reset_engine_for_tests  # noqa: E402
from app.main import app  # noqa: E402


def test_auth_full_flow() -> None:
    get_settings.cache_clear()  # type: ignore[attr-defined]
    reset_engine_for_tests()
    ensure_schema()

    client = TestClient(app)

    # --- register ---
    r = client.post(
        "/auth/register",
        json={
            "email": "alice.auth@eventive.dev",
            "password": "hunter2!",
            "name": "Alice Auth",
            "headline": "AI engineer",
        },
    )
    assert r.status_code == 201, r.text
    pair = r.json()
    assert pair["token_type"] == "bearer"
    assert pair["access_token"]
    assert pair["refresh_token"] != pair["access_token"]
    assert pair["user"]["email"] == "alice.auth@eventive.dev"
    assert pair["user"]["id"] > 0

    # Regression: `/auth/register` MUST synchronously populate the new user's
    # `vec_user_profile` row (via user_service.create_user) so recommendations
    # work on the very next request — no manual /ai/embed/user/{id} needed.
    from sqlalchemy import text as sql_text

    from app.infra.db import SessionLocal

    with SessionLocal() as db:
        row = db.execute(
            sql_text("SELECT embedding FROM vec_user_profile WHERE user_id = :k"),
            {"k": pair["user"]["id"]},
        ).first()
        assert row is not None, (
            "register did not populate vec_user_profile — recommendations "
            "would silently return empty for the new account"
        )

    # duplicate email is rejected
    r_dup = client.post(
        "/auth/register",
        json={"email": "alice.auth@eventive.dev", "password": "hunter2!", "name": "Dup"},
    )
    assert r_dup.status_code == 409

    access = pair["access_token"]
    refresh = pair["refresh_token"]
    auth_headers = {"Authorization": f"Bearer {access}"}

    # --- me works with the fresh token ---
    r = client.get("/auth/me", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["email"] == "alice.auth@eventive.dev"

    # --- me fails without a token ---
    assert client.get("/auth/me").status_code == 401

    # --- me fails with a bogus token ---
    assert (
        client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"}).status_code
        == 401
    )

    # --- login works with the same credentials ---
    r = client.post(
        "/auth/login",
        json={"email": "alice.auth@eventive.dev", "password": "hunter2!"},
    )
    assert r.status_code == 200
    logged_in = r.json()
    assert logged_in["user"]["id"] == pair["user"]["id"]

    # --- login fails with the wrong password ---
    r = client.post(
        "/auth/login",
        json={"email": "alice.auth@eventive.dev", "password": "wrong"},
    )
    assert r.status_code == 401

    # --- refresh rotates the tokens ---
    r = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200, r.text
    rotated = r.json()
    assert rotated["access_token"] != access
    assert rotated["refresh_token"] != refresh

    # --- reusing the old refresh token now fails (rotation revokes prior) ---
    r = client.post("/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 401

    # --- logout invalidates the current refresh token ---
    new_refresh = rotated["refresh_token"]
    r = client.post("/auth/logout", json={"refresh_token": new_refresh})
    assert r.status_code == 204

    r = client.post("/auth/refresh", json={"refresh_token": new_refresh})
    assert r.status_code == 401

    # --- login twice, then logout-all revokes both ---
    a = client.post(
        "/auth/login", json={"email": "alice.auth@eventive.dev", "password": "hunter2!"}
    ).json()
    b = client.post(
        "/auth/login", json={"email": "alice.auth@eventive.dev", "password": "hunter2!"}
    ).json()
    r = client.post(
        "/auth/logout-all", headers={"Authorization": f"Bearer {a['access_token']}"}
    )
    assert r.status_code == 200
    assert r.json()["revoked"] >= 2
    for token in (a["refresh_token"], b["refresh_token"]):
        assert (
            client.post("/auth/refresh", json={"refresh_token": token}).status_code == 401
        )
