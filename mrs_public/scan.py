"""Look for a local runtime only after the user says yes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class Scan:
    ok: bool
    runtime: str
    models: tuple[str, ...]
    reason: str


def scan_ollama(
    host: str = "http://127.0.0.1:11434",
    *,
    permission: bool,
    opener: Callable[..., object] | None = None,
    timeout: float = 3,
) -> Scan:
    if not permission:
        return Scan(False, "ollama", (), "Need permission before I look at installed models.")
    fetch = opener or urlopen
    url = host.rstrip("/") + "/api/tags"
    try:
        with fetch(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        return Scan(False, "ollama", (), f"Ollama is not answering at {host}. {exc.reason}")
    except Exception as exc:  # noqa: BLE001 — first boot must say what failed
        return Scan(False, "ollama", (), f"Ollama is not answering at {host}. {type(exc).__name__}: {exc}")
    names = []
    for raw in payload.get("models") or []:
        name = raw.get("name") if isinstance(raw, dict) else None
        if name:
            names.append(str(name))
    if not names:
        return Scan(False, "ollama", (), "Ollama is up and has no models installed.")
    return Scan(True, "ollama", tuple(names), "")
