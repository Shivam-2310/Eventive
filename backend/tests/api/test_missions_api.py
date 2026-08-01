"""Missions REST: create, list, /me."""
from __future__ import annotations


def _mk_user(client, email: str) -> int:  # noqa: ANN001
    return client.post("/users", json={"email": email, "name": "U"}).json()["id"]


def test_seed_lists_four_missions(seeded, client) -> None:  # noqa: ANN001, ARG001
    body = client.get("/missions").json()
    assert len(body) >= 4
    titles = {m["title"] for m in body}
    assert "AI track streak" in titles


def test_create_mission(client) -> None:  # noqa: ANN001
    r = client.post(
        "/missions",
        json={
            "title": "Custom Mission",
            "description": "test",
            "rule": {"type": "like_events", "count": 2},
            "points": 5,
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Custom Mission"
    assert body["rule"] == {"type": "like_events", "count": 2}


def test_missions_me_shape(seeded, client) -> None:  # noqa: ANN001, ARG001
    uid = _mk_user(client, "me@x.com")
    body = client.get(f"/missions/me?user_id={uid}").json()
    assert isinstance(body, list)
    for row in body:
        assert "mission" in row
        # progress may be None until recompute() is triggered.
