"""Refuse private house language in anything this app would ship as a prompt."""

from __future__ import annotations

FORBIDDEN = (
    "danny",
    "dray",
    "d-ray",
    "covenant",
    "pearl leaf",
    "millaflex",
    "/home/milla",
    "bluez",
    "ear cuff",
    "earcuff",
    "wife",
    "husband",
    "devmilla",
    "shared_chat",
)


def leaks(text: str) -> list[str]:
    low = (text or "").lower()
    return [word for word in FORBIDDEN if word in low]
