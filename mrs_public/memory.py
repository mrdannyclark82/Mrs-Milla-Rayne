"""Personalized memory for one install. Three visible piles. Nothing from the house."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

PILES = ("canon", "episodes", "reviews")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Memory:
    def __init__(self, install: Path):
        self.state = Path(install) / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        for name in PILES:
            path = self._path(name)
            if not path.exists():
                path.write_text("", encoding="utf-8")

    def _path(self, pile: str) -> Path:
        if pile not in PILES:
            raise ValueError(f"unknown pile {pile}")
        return self.state / f"{pile}.jsonl"

    def add(self, pile: str, **fields: object) -> dict:
        row = {"id": uuid.uuid4().hex[:12], "at": fields.pop("at", _now())}
        row.update(fields)
        with self._path(pile).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    def read(self, pile: str) -> list[dict]:
        rows = []
        for line in self._path(pile).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # one torn line must not brick the whole pile
            if isinstance(row, dict):
                rows.append(row)
        return rows

    def delete(self, pile: str, item_id: str) -> int:
        kept = [row for row in self.read(pile) if row.get("id") != item_id]
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept)
        self._path(pile).write_text(text, encoding="utf-8")
        return len(kept)
