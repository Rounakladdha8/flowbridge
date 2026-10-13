import logging
import re

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from . import calendar_api, db, extract, policies

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rta")

app = FastAPI(title="Request-to-Action")
db.init()


class Body(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ApprovalBody(BaseModel):
    preview_id: str = Field(min_length=1, max_length=128)


def require_text(body):
    text = body.text.strip()
    if not text:
        raise HTTPException(422, "text is required")
    return text


def find_request(rid):
    request = db.get_request(rid)
    if not request:
        raise HTTPException(404, "Request not found")
    return request


def evaluate(text, info):
    info = dict(info)
    info["missing"] = [
        name for name in extract.REQUIRED
        if not info.get(name)
    ]

    if not info["in_scope"]:
        return info, [], "rejected"

    citations = policies.hours_evidence()
    citations.extend(
        citation
        for citation in policies.search(text)
        if citation["source"] != "hours.md"
    )

    if info.get("time_window"):
        issue = policies.check_schedule(info)
        if issue:
            info["missing"].append(issue)

    status = "needs_info" if info["missing"] else "ready"
    return info, citations, status


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/requests")
def create_request(body: Body):
    text = require_text(body)
    info, citations, status = evaluate(
        text, extract.extract(text)
    )
    rid = db.insert_request(text, info, citations, status)
    log.info("request=%s status=%s", rid, status)
    return db.get_request(rid)


@app.post("/requests/{rid}/clarify")
def clarify(rid: int, body: Body):
    request = find_request(rid)

    if request["status"] != "needs_info":
        raise HTTPException(
            409, "This request is not awaiting clarification"
        )

    reply = require_text(body)
    combined = (
        request["text"] + "\nCustomer clarification: " + reply
    )

    info = dict(request["extracted"])
    changes = extract.extract(reply)

    normalized = reply.lower()
    day = re.search(extract.DAY_PATTERN, normalized)
    part = re.search(extract.PART_PATTERN, normalized)

    if day or part:
        changes["time_window"] = " ".join(
            match.group(0)
            for match in (day, part)
            if match is not None
        )

    for name in extract.REQUIRED:
        if changes.get(name):
            info[name] = changes[name]

    info, citations, status = evaluate(combined, info)
    db.update_request(rid, combined, info, citations, status)
    return db.get_request(rid)


@app.post("/requests/{rid}/preview")
def preview(rid: int):
    request = find_request(rid)

    if request["status"] not in ("ready", "failed"):
        raise HTTPException(
            409, "Only ready or failed requests can be previewed"
        )

    info, _, status = evaluate(
        request["text"], request["extracted"]
    )
    if status != "ready":
        raise HTTPException(
            409, "Clarification is required before preview"
        )

    try:
        return calendar_api.preview_event(f"req-{rid}", info)
    except calendar_api.ConnectorError as error:
        raise HTTPException(409, str(error)) from error


@app.post("/requests/{rid}/approve")
def approve(rid: int, body: ApprovalBody):
    request = find_request(rid)

    if request["status"] == "booked":
        if request["booking_id"] != body.preview_id:
            raise HTTPException(409, "Booking ID does not match")
        return request

    if request["status"] not in ("ready", "failed"):
        raise HTTPException(
            409, "This request cannot be approved"
        )

    info, citations, status = evaluate(
        request["text"], request["extracted"]
    )

    if status != "ready":
        db.update_request(
            rid, request["text"], info, citations, status
        )
        return db.get_request(rid)

    try:
        # Reuses the saved proposal; does not choose a new date.
        proposal = calendar_api.preview_event(f"req-{rid}", info)
        if proposal["preview_id"] != body.preview_id:
            raise HTTPException(
                409, "Preview changed. Reload before approving."
            )

        event = calendar_api.create_event(f"req-{rid}", info)
        db.mark(rid, "booked", booking_id=event["id"])
        db.log_exec(rid, True, event["id"])
        log.info("request=%s booked", rid)

    except calendar_api.ConnectorError as error:
        db.mark(rid, "failed", error=str(error))
        db.log_exec(rid, False, str(error))
        log.warning("request=%s connector failed", rid)

    return db.get_request(rid)


@app.get("/requests")
def list_all():
    return db.list_requests()


@app.get("/requests/{rid}")
def get_one(rid: int):
    request = find_request(rid)
    return {
        **request,
        "executions": db.executions(rid),
    }


@app.post("/debug/fail-next")
def force_fail(n: int = Query(default=1, ge=1, le=3)):
    # Local demo only. Protect or disable before deployment.
    calendar_api.fail_next(n)
    return {"fail_next": n}