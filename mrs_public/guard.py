"""Refuse private language in anything this app would ship as a prompt.

The shipped build carries no private word list of its own. An install adds
its own terms, one per line, in a plain text file that lives with the
install and never in this repository:

- the path named by the MRS_PUBLIC_GUARD_TERMS environment variable, or
- ``state/guard_terms.txt`` inside the install directory
  (``~/.mrs-milla-rayne`` by default).

Matching is a plain substring check, case-insensitive. The terms are the
install's business, not the build's.
"""

from __future__ import annotations

import os
from pathlib import Path

FORBIDDEN: tuple[str, ...] = ()


def _terms_file() -> Path:
    override = os.environ.get("MRS_PUBLIC_GUARD_TERMS")
    if override:
        return Path(override)
    return Path.home() / ".mrs-milla-rayne" / "state" / "guard_terms.txt"


def _load_terms() -> tuple[str, ...]:
    try:
        lines = _terms_file().read_text(encoding="utf-8").splitlines()
    except OSError:
        return ()
    return tuple(line.strip().lower() for line in lines if line.strip())


def leaks(text: str) -> list[str]:
    low = (text or "").lower()
    return [word for word in FORBIDDEN + _load_terms() if word in low]
