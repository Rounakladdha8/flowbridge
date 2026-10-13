import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

import httplib2
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from . import db

ROOT = Path(__file__).resolve().parent.parent
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

log = logging.getLogger(__name__)
_lock = Lock()
_failures = 0

DAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


class ConnectorError(Exception):
    pass


def fail_next(n=1):
    global _failures

    with _lock:
        _failures = n


def _service():
    token_file = ROOT / "token.json"

    if not token_file.exists():
        raise ConnectorError(
            "Calendar authorization missing. "
            "Run authorize_calendar.py."
        )

    credentials = Credentials.from_authorized_user_file(
        str(token_file),
        SCOPES,
    )

    if not credentials.valid:
        if not credentials.refresh_token:
            raise ConnectorError(
                "Please run authorize_calendar.py again."
            )

        credentials.refresh(Request())

        token_file.write_text(
            credentials.to_json(),
            encoding="utf-8",
        )

    return build(
        "calendar",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def _booking_body(key, details, calendar_id, timezone):
    # Save the chosen date and event ID before contacting Google.
    # Retrying the same request reuses these saved values.
    with db.conn() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS calendar_jobs (
                job_key TEXT PRIMARY KEY,
                calendar_id TEXT NOT NULL,
                body TEXT NOT NULL
            )
        """)

        saved = connection.execute(
            """
            SELECT calendar_id, body
            FROM calendar_jobs
            WHERE job_key = ?
            """,
            (key,),
        ).fetchone()

        if saved:
            if saved["calendar_id"] != calendar_id:
                raise ConnectorError(
                    "Calendar configuration changed "
                    "for this request."
                )

            return json.loads(saved["body"])

        now = datetime.now(ZoneInfo(timezone))
        window = (
            details.get("time_window") or ""
        ).lower().strip()

        day = re.search(
            r"\b(today|tomorrow|monday|tuesday|"
            r"wednesday|thursday|friday|saturday|sunday)\b",
            window,
        )

        part = re.search(
            r"\b(morning|afternoon)\b",
            window,
        )

        if not day or not part:
            raise ConnectorError(
                "A specific day and morning/afternoon "
                "are required."
            )

        if re.search(r"\bevening\b", window):
            raise ConnectorError(
                "Choose morning or afternoon."
            )

        name = day.group(1)

        if name == "today":
            raise ConnectorError(
                "Same-day bookings require staff review."
            )

        if name == "tomorrow":
            booking_date = now.date() + timedelta(days=1)
        else:
            offset = (
                DAYS[name] - now.weekday()
            ) % 7

            # Named weekdays mean the next occurrence.
            booking_date = (
                now.date() + timedelta(days=offset or 7)
            )

        if booking_date.weekday() == 6:
            raise ConnectorError(
                "Sunday bookings are not supported."
            )

        # Fixed demo slots:
        # morning = 09:00–10:00
        # afternoon = 13:00–14:00
        hour = (
            9 if part.group(1) == "morning" else 13
        )

        start = datetime(
            booking_date.year,
            booking_date.month,
            booking_date.day,
            hour,
            tzinfo=ZoneInfo(timezone),
        )

        end = start + timedelta(hours=1)

        body = {
            "id": uuid.uuid4().hex,
            "summary": (
                "DEMO — "
                f"{details.get('service_type', 'Service')} visit"
            ),
            "description": (
                f"Request: {key}\n"
                f"Requested window: {window}\n"
                "Portfolio demonstration booking."
            ),
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": timezone,
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": timezone,
            },
            "extendedProperties": {
                "private": {
                    "request_key": key,
                },
            },
            "reminders": {
                "useDefault": False,
            },
        }

        connection.execute(
            """
            INSERT INTO calendar_jobs (
                job_key,
                calendar_id,
                body
            )
            VALUES (?, ?, ?)
            """,
            (
                key,
                calendar_id,
                json.dumps(body),
            ),
        )

        return body


def _existing(service, calendar_id, event_id):
    try:
        event = service.events().get(
            calendarId=calendar_id,
            eventId=event_id,
        ).execute()

        if event.get("status") == "cancelled":
            raise ConnectorError(
                "The saved calendar event was cancelled. "
                "Staff review is needed."
            )

        return event

    except HttpError as error:
        if error.resp.status == 404:
            return None

        raise


def _check_availability(service, calendar_id, body):
    page_token = None

    while True:
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=body["start"]["dateTime"],
            timeMax=body["end"]["dateTime"],
            singleEvents=True,
            showDeleted=False,
            maxResults=250,
            pageToken=page_token,
        ).execute()

        for event in result.get("items", []):
            if event.get("id") == body["id"]:
                continue

            if event.get("status") == "cancelled":
                continue

            # Events marked "free" do not occupy the slot.
            if event.get("transparency") == "transparent":
                continue

            raise ConnectorError(
                "This time slot is already occupied. "
                "Create a new request for another day "
                "or time window."
            )

        page_token = result.get("nextPageToken")

        if not page_token:
            return


def create_event(idempotency_key, details):
    global _failures

    # Serializes calls within this one server process.
    # This is not a cross-process or cross-application lock.
    with _lock:
        try:
            config_file = ROOT / "calendar_config.json"

            if not config_file.exists():
                raise ConnectorError(
                    "calendar_config.json is missing. "
                    "Place it beside token.json."
                )

            config = json.loads(
                config_file.read_text(
                    encoding="utf-8"
                )
            )

            calendar_id = config["calendar_id"].strip()
            timezone = config.get(
                "timezone",
                "America/Chicago",
            )

            if (
                not calendar_id
                or calendar_id == "primary"
                or "PASTE_" in calendar_id
            ):
                raise ConnectorError(
                    "Configure the separate demo calendar ID."
                )

            body = _booking_body(
                idempotency_key,
                details,
                calendar_id,
                timezone,
            )

            service = _service()

            # Recover a previously created event first.
            existing = _existing(
                service,
                calendar_id,
                body["id"],
            )

            if existing:
                return existing

            if _failures > 0:
                _failures -= 1

                raise ConnectorError(
                    "Simulated calendar timeout; "
                    "retry is available."
                )

            start = datetime.fromisoformat(
                body["start"]["dateTime"]
            )

            if start <= datetime.now(ZoneInfo(timezone)):
                raise ConnectorError(
                    "Saved booking time has passed. "
                    "Create a new request."
                )

            _check_availability(
                service,
                calendar_id,
                body,
            )

            try:
                return service.events().insert(
                    calendarId=calendar_id,
                    body=body,
                    sendUpdates="none",
                ).execute()

            except HttpError as error:
                # Recover if the same event ID already exists.
                if error.resp.status == 409:
                    existing = _existing(
                        service,
                        calendar_id,
                        body["id"],
                    )

                    if existing:
                        return existing

                raise

        except ConnectorError:
            raise

        except HttpError as error:
            log.warning(
                "Calendar API returned HTTP %s",
                error.resp.status,
            )

            raise ConnectorError(
                f"Google Calendar returned HTTP "
                f"{error.resp.status}. "
                "Check calendar access or retry "
                "if temporary."
            ) from error

        except (
            GoogleAuthError,
            httplib2.HttpLib2Error,
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            log.warning(
                "Calendar connector failed: %s",
                type(error).__name__,
            )

            raise ConnectorError(
                "Calendar connection failed. "
                "Check configuration, authorization, "
                "and network access."
            ) from error

def preview_event(idempotency_key, details):
    """Save a proposed booking without creating a Google event."""
    with _lock:
        try:
            config = json.loads(
                (ROOT / "calendar_config.json").read_text(
                    encoding="utf-8"
                )
            )

            calendar_id = config["calendar_id"].strip()
            timezone = config.get("timezone", "America/Chicago")

            if (
                not calendar_id
                or calendar_id == "primary"
                or "PASTE_" in calendar_id
            ):
                raise ConnectorError(
                    "Configure the separate demo calendar ID."
                )

            body = _booking_body(
                idempotency_key,
                details,
                calendar_id,
                timezone,
            )

            return {
                "preview_id": body["id"],
                "title": body["summary"],
                "start": body["start"]["dateTime"],
                "end": body["end"]["dateTime"],
                "timezone": body["start"]["timeZone"],
            }

        except ConnectorError:
            raise

        except (OSError, ValueError, KeyError, TypeError) as error:
            raise ConnectorError(
                "Cannot prepare booking preview. "
                "Check calendar_config.json."
            ) from error        