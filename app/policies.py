import pathlib
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DIR = pathlib.Path(__file__).resolve().parent.parent / "policies"
TIMEZONE = "America/Chicago"

DAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

STOP_WORDS = {
    "a", "an", "the", "and", "or", "to", "of", "for",
    "in", "on", "at", "by", "with", "from", "is", "are",
    "was", "be", "been", "it", "this", "that", "these",
    "those", "i", "we", "you", "my", "our", "your",
    "me", "us", "can", "could", "would", "should",
    "please", "need", "someone", "call", "email",
    "customer", "clarification",
}

TOPICS = {
    "cancellation.md": (
        r"\b(?:cancel(?:led|ed|ling|ing|lation|lations)?|"
        r"reschedul(?:e|ed|ing)|refund(?:s|ed)?|"
        r"fee(?:s)?|penalt(?:y|ies)|no[\s-]?show)\b"
    ),
    "service_area.md": (
        r"\b(?:service\s+area|coverage|zip(?:\s+code)?|"
        r"postal\s+code|address|location|outside|"
        r"out[\s-]of[\s-]area|serve|serves|serving|"
        r"travel|radius)\b"
        r"|\b\d{5}(?:-\d{4})?\b"
    ),
}


def _tokens(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z]+", text.lower())
        if word not in STOP_WORDS
    }


def search(query: str, k: int = 2):
    """Topic-aware keyword retrieval; not embedding-based RAG."""
    if k <= 0:
        return []

    normalized = query.lower()
    tokens = _tokens(query)
    hits = []

    for file in sorted(DIR.glob("*.md")):
        # Hours are always supplied separately.
        if file.name == "hours.md":
            continue

        topic = TOPICS.get(file.name)

        # Known policy topics must actually appear in the query.
        if topic and not re.search(topic, normalized):
            continue

        paragraphs = re.split(
            r"\n\s*\n",
            file.read_text(encoding="utf-8"),
        )

        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph:
                continue

            score = len(tokens & _tokens(paragraph))

            # Permit related wording such as cancel/cancellation.
            if topic:
                score += 1

            if score:
                hits.append({
                    "source": file.name,
                    "text": paragraph,
                    "score": score,
                })

    return sorted(
        hits,
        key=lambda hit: (
            -hit["score"],
            hit["source"],
            hit["text"],
        ),
    )[:k]


def hours_evidence():
    file = DIR / "hours.md"

    if not file.exists():
        return []

    text = file.read_text(encoding="utf-8").strip()
    if not text:
        return []

    return [{
        "source": file.name,
        "text": text,
        "score": 0,
    }]


def check_schedule(info: dict, now=None):
    """Require a supported day and a daytime window."""
    window = (info.get("time_window") or "").lower().strip()

    if not window:
        return "time_window"

    now = now or datetime.now(ZoneInfo(TIMEZONE))

    day_match = re.search(
        r"\b(today|tomorrow|monday|tuesday|wednesday|"
        r"thursday|friday|saturday|sunday)\b",
        window,
    )

    if not day_match:
        return "specific_day_required"

    day = day_match.group(1)

    if day == "today":
        weekday = now.weekday()
    elif day == "tomorrow":
        weekday = (now + timedelta(days=1)).weekday()
    else:
        weekday = DAYS[day]

    if weekday == 6:
        return "choose_monday_to_saturday"

    if day == "today":
        return "same_day_requires_staff_review_choose_future_day"

    if re.search(r"\bevening\b", window):
        return "choose_morning_or_afternoon"

    if not re.search(r"\b(morning|afternoon)\b", window):
        return "specify_morning_or_afternoon"

    return None