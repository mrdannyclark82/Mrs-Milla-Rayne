"""Classify installed tags. Never auto-picks a house weight."""

from __future__ import annotations

import os
from pathlib import Path

from .names import CODER_HINTS, EMBED_HINTS, HOUSE_BASES, VISION_HINTS


def base_name(tag: str) -> str:
    return (tag or "").strip().lower().split(":", 1)[0]


def _private_bases_file() -> Path:
    override = os.environ.get("MRS_PUBLIC_PRIVATE_BASES")
    if override:
        return Path(override)
    return Path.home() / ".mrs-milla-rayne" / "state" / "private_bases.txt"


def _install_private_bases() -> frozenset[str]:
    """Base names the install calls private, one per line, from its own file.

    Same discipline as the guard terms: the shipped build carries no house
    list of its own; the install names its weights and they stay home.
    """
    try:
        lines = _private_bases_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return frozenset()
    return frozenset(base_name(line) for line in lines if line.strip())


def is_house(tag: str) -> bool:
    return base_name(tag) in HOUSE_BASES or base_name(tag) in _install_private_bases()


def is_cloud(tag: str) -> bool:
    """A `:cloud` tag runs on the provider's machines, not this one.

    Cloud tags stay in the list — badged — but auto-setup never picks
    one, and a reply from one is never called local.
    """
    return (tag or "").strip().lower().endswith(":cloud")


def _has(tag: str, hints: tuple[str, ...]) -> bool:
    low = (tag or "").lower()
    return any(hint in low for hint in hints)


def is_coder(tag: str) -> bool:
    return _has(tag, CODER_HINTS) and not is_house(tag)


def is_vision(tag: str) -> bool:
    return _has(tag, VISION_HINTS) and not is_house(tag) and not is_embed(tag)


def is_embed(tag: str) -> bool:
    return _has(tag, EMBED_HINTS) and not is_house(tag)


def public_tags(tags: list[str]) -> list[str]:
    return [tag for tag in tags if tag and not is_house(tag)]


def suggest(tags: list[str]) -> dict[str, str | None]:
    """Pick defaults. House and cloud tags are invisible to auto. Coder names win the code role."""
    usable = [tag for tag in public_tags(tags) if not is_cloud(tag)]
    coder = next((tag for tag in usable if is_coder(tag)), None)
    vision = next((tag for tag in usable if is_vision(tag)), None)
    embed = next((tag for tag in usable if is_embed(tag)), None)
    plain = [
        tag
        for tag in usable
        if not is_coder(tag) and not is_vision(tag) and not is_embed(tag)
    ]
    chat = plain[0] if plain else next(
        (tag for tag in usable if not is_embed(tag) and not is_vision(tag)),
        None,
    )
    return {
        "companion": chat,
        "code": coder or chat,
        "vision": vision,
        "embed": embed,
        "code_reason": (
            f"{coder} has code, coder, or coding in the name."
            if coder
            else "No code-named model is installed. The code role can use the companion weights with its own prompt."
        ),
    }
