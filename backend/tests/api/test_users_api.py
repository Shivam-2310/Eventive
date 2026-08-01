"""Users REST endpoints + /users/{id}/wrapped."""
from __future__ import annotations


def test_create_get_list_users(client) -> None:  # noqa: ANN001
    r = client.post("/users", json={"email": "a@x.com", "name": "A"})
    assert r.status_code == 201, r.text
    user = r.json()
    assert user["id"] > 0
    assert user["email"] == "a@x.com"

    r = client.get(f"/users/{user['id']}")
    assert r.status_code == 200

    r = client.get("/users")
    assert r.status_code == 200
    assert any(u["id"] == user["id"] for u in r.json())


def test_duplicate_email_returns_409(client) -> None:  # noqa: ANN001
    client.post("/users", json={"email": "dup@x.com", "name": "A"})
    r = client.post("/users", json={"email": "dup@x.com", "name": "B"})
    assert r.status_code == 409


def test_patch_and_delete_user(client) -> None:  # noqa: ANN001
    r = client.post("/users", json={"email": "p@x.com", "name": "P"})
    uid = r.json()["id"]
    r = client.patch(f"/users/{uid}", json={"headline": "hi", "opt_in_networking": False})
    assert r.status_code == 200
    assert r.json()["headline"] == "hi"
    assert r.json()["opt_in_networking"] is False

    r = client.delete(f"/users/{uid}")
    assert r.status_code == 204
    r = client.get(f"/users/{uid}")
    assert r.status_code == 404


def test_get_and_patch_missing_user_returns_404(client) -> None:  # noqa: ANN001
    assert client.get("/users/999999").status_code == 404
    assert client.patch("/users/999999", json={"name": "x"}).status_code == 404
    assert client.delete("/users/999999").status_code == 404


def test_wrapped_endpoint_shape(seeded, client) -> None:  # noqa: ANN001, ARG001
    """After seed, alice (user id 2) has interactions + accepted connections."""
    r = client.get("/users/2/wrapped")
    assert r.status_code == 200
    body = r.json()
    assert body["sessions_attended"] >= 1
    assert body["connections_made"] >= 1
    assert isinstance(body["top_topics"], list) and body["top_topics"]


def test_set_and_get_user_interests(seeded, client) -> None:  # noqa: ANN001, ARG001
    # pick a fresh user
    r = client.post("/users", json={"email": "ui@x.com", "name": "UI"})
    uid = r.json()["id"]

    all_interests = client.get("/interests").json()
    topic_ids = [i["id"] for i in all_interests if i["category"] == "topic"][:3]
    r = client.put(f"/users/{uid}/interests", json={"interest_ids": topic_ids, "blurb": "hey"})
    assert r.status_code == 200
    assert r.json()["count"] == 3

    got = client.get(f"/users/{uid}/interests").json()
    assert len(got) == 3
    ids_got = [entry["interest_id"] for entry in got]
    assert set(ids_got) == set(topic_ids)


def test_set_user_interests_missing_user_returns_404(client) -> None:  # noqa: ANN001
    r = client.put("/users/999999/interests", json={"interest_ids": [], "blurb": None})
    assert r.status_code == 404
