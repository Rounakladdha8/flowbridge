import pytest
from fastapi.testclient import TestClient


GOOD = (
    "Need a plumber Wednesday morning. "
    "Call 312-555-0100."
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Isolate each test from your real database and AI API.
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    from app import calendar_api, db
    from app.main import app

    db.init()

    state = {
        "events": {},
        "failures": 0,
        "created": 0,
    }

    def preview_event(key, details):
        return {
            "preview_id": f"demo-{key}",
            "title": f"DEMO — {details['service_type']} visit",
            "start": "2026-10-14T09:00:00-05:00",
            "end": "2026-10-14T10:00:00-05:00",
            "timezone": "America/Chicago",
        }

    def create_event(key, details):
        # Model an idempotent connector without contacting Google.
        if key in state["events"]:
            return state["events"][key]

        if state["failures"]:
            state["failures"] -= 1
            raise calendar_api.ConnectorError(
                "Simulated calendar timeout; retry is available."
            )

        event = {"id": preview_event(key, details)["preview_id"]}
        state["events"][key] = event
        state["created"] += 1
        return event

    def fail_next(n=1):
        state["failures"] = n

    monkeypatch.setattr(calendar_api, "preview_event", preview_event)
    monkeypatch.setattr(calendar_api, "create_event", create_event)
    monkeypatch.setattr(calendar_api, "fail_next", fail_next)

    with TestClient(app) as test_client:
        yield test_client, state


def create(client, text=GOOD):
    response = client.post("/requests", json={"text": text})
    assert response.status_code == 200, response.text
    return response.json()


def preview(client, rid):
    response = client.post(f"/requests/{rid}/preview")
    assert response.status_code == 200, response.text
    return response.json()


def approve(client, rid, preview_id):
    return client.post(
        f"/requests/{rid}/approve",
        json={"preview_id": preview_id},
    )


def test_valid_request_preview_and_booking(client):
    c, state = client
    request = create(c)

    assert request["status"] == "ready"
    assert request["citations"]
    assert state["created"] == 0

    proposal = preview(c, request["id"])

    assert proposal["timezone"] == "America/Chicago"
    assert state["created"] == 0  # Preview does not book.

    response = approve(c, request["id"], proposal["preview_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "booked"
    assert response.json()["booking_id"] == proposal["preview_id"]
    assert state["created"] == 1


def test_missing_info_then_clarify(client):
    c, _ = client
    request = create(c, "My AC stopped working.")

    assert request["status"] == "needs_info"
    assert "contact" in request["extracted"]["missing"]

    response = c.post(
        f"/requests/{request['id']}/clarify",
        json={"text": "Wednesday morning. Email a@b.com."},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "ready"
    assert updated["extracted"]["service_type"] == "hvac"
    assert updated["extracted"]["time_window"] == "wednesday morning"
    assert updated["extracted"]["contact"] == "a@b.com"


def test_sunday_blocked_then_corrected(client):
    c, state = client
    request = create(
        c,
        "Need a plumber Sunday afternoon. Call 312-555-0100.",
    )

    assert request["status"] == "needs_info"
    assert (
        "choose_monday_to_saturday"
        in request["extracted"]["missing"]
    )

    response = approve(c, request["id"], "unapproved")
    assert response.status_code == 409
    assert state["created"] == 0

    response = c.post(
        f"/requests/{request['id']}/clarify",
        json={"text": "Monday morning instead."},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["status"] == "ready"
    assert updated["extracted"]["time_window"] == "monday morning"
    assert updated["extracted"]["service_type"] == "plumbing"
    assert updated["extracted"]["contact"] == "312-555-0100"
    assert updated["extracted"]["missing"] == []


def test_off_topic_rejected(client):
    c, state = client
    request = create(c, "Can someone explain my account charges?")

    assert request["status"] == "rejected"
    assert c.post(
        f"/requests/{request['id']}/preview"
    ).status_code == 409
    assert approve(
        c, request["id"], "unapproved"
    ).status_code == 409
    assert state["created"] == 0


def test_failure_then_retry(client):
    c, state = client
    request = create(c)
    proposal = preview(c, request["id"])

    assert c.post("/debug/fail-next").status_code == 200

    first = approve(c, request["id"], proposal["preview_id"])
    assert first.status_code == 200
    assert first.json()["status"] == "failed"
    assert state["created"] == 0

    second = approve(c, request["id"], proposal["preview_id"])
    assert second.status_code == 200
    assert second.json()["status"] == "booked"
    assert second.json()["error"] is None
    assert state["created"] == 1

    history = c.get(f"/requests/{request['id']}").json()
    assert [entry["ok"] for entry in history["executions"]] == [0, 1]


def test_double_approval_no_duplicate(client):
    c, state = client
    request = create(c)
    proposal = preview(c, request["id"])

    first = approve(c, request["id"], proposal["preview_id"])
    second = approve(c, request["id"], proposal["preview_id"])

    assert first.status_code == second.status_code == 200
    assert first.json()["booking_id"] == second.json()["booking_id"]
    assert state["created"] == 1

    history = c.get(f"/requests/{request['id']}").json()
    assert len(history["executions"]) == 1


def test_wrong_preview_cannot_book(client):
    c, state = client
    request = create(c)
    preview(c, request["id"])

    response = approve(c, request["id"], "wrong-preview-id")

    assert response.status_code == 409
    assert state["created"] == 0
    assert c.get(
        f"/requests/{request['id']}"
    ).json()["status"] == "ready"


def test_approval_requires_preview_id(client):
    c, state = client
    request = create(c)

    response = c.post(f"/requests/{request['id']}/approve")

    assert response.status_code == 422
    assert state["created"] == 0


def test_blank_request_rejected(client):
    c, _ = client

    response = c.post("/requests", json={"text": "   "})

    assert response.status_code == 422
    assert c.get("/requests").json() == []