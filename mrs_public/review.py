"""On-open review of this install's episodes. It writes a review. It does not edit the prompt."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .memory import Memory

DAY = timedelta(hours=24)
MISS_MARKS = (
    "that's wrong",
    "thats wrong",
    "not what i",
    "you missed",
    "try again",
)


def _parse(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def review_due(last_at: str | None, now: datetime) -> bool:
    if not last_at:
        return True
    return now - _parse(last_at) >= DAY


def split_outcomes(episodes: list[dict]) -> tuple[list[str], list[str]]:
    worked: list[str] = []
    missed: list[str] = []
    for episode in episodes:
        text = str(episode.get("text") or "").lower()
        outcome = episode.get("outcome")
        if outcome == "missed" or any(mark in text for mark in MISS_MARKS):
            missed.append(str(episode["id"]))
        elif outcome in {"done", "worked"} or episode.get("files"):
            worked.append(str(episode["id"]))
    return worked, missed


def on_open(
    memory: Memory,
    now: datetime,
    *,
    background: bool = False,
    allow_background: bool = False,
) -> dict:
    if background and not allow_background:
        return {"ran": False, "reason": "Background review is off. She reviews when the app opens."}
    reviews = memory.read("reviews")
    last = reviews[-1]["at"] if reviews else None
    if not review_due(last, now):
        return {"ran": False, "reason": "Reviewed within the last day."}
    since = [row for row in memory.read("episodes") if last is None or row["at"] > last]
    worked, missed = split_outcomes(since)
    row = memory.add(
        "reviews",
        at=now.replace(microsecond=0).isoformat(),
        kind="structural",
        episode_ids=[row["id"] for row in since],
        worked=worked,
        missed=missed,
        note="Structural review of this install. The public prompt was not changed.",
    )
    return {"ran": True, "review": row}
