"""Skills: written know-how the install can teach her, one file each.

A skill is a markdown file in the install's skills/ folder:

    name: Meal Planner
    when: meal plan, recipe, grocery list

    <the instructions>

Skills are instructions, never powers. A skill can tell her how to do a
task well; it cannot run anything, open anything, or grant anything.
At most one skill rides a turn — the first whose "when" phrases appear
in what the user said — and its name is reported on the page. The
folder is the install's own; this build ships no skills of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_SKILL_CHARS = 6000
SKIP_NAMES = {"readme.md"}


@dataclass(frozen=True)
class Skill:
    name: str
    triggers: tuple[str, ...]
    body: str


def skills_dir(install: Path) -> Path:
    return Path(install) / "skills"


def _parse(path: Path) -> Skill | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()
    name = ""
    triggers: list[str] = []
    idx = 0
    while idx < len(lines):
        line = lines[idx].strip()
        if line == "---":
            idx += 1
            break
        if ":" in line and not line.startswith("#"):
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key == "name":
                name = value.strip()
            elif key == "when":
                triggers = [t.strip().lower() for t in value.split(",") if t.strip()]
            else:
                break
            idx += 1
            continue
        break
    body = "\n".join(lines[idx:]).strip()[:MAX_SKILL_CHARS]
    if not body:
        return None
    return Skill(name or path.stem, tuple(triggers), body)


def load_skills(install: Path) -> list[Skill]:
    folder = skills_dir(install)
    if not folder.is_dir():
        return []
    found = []
    for path in sorted(folder.glob("*.md")):
        if path.name.lower() in SKIP_NAMES or path.name.startswith((".", "_")):
            continue
        skill = _parse(path)
        if skill is not None:
            found.append(skill)
    return found


def pick_skill(skills: list[Skill], text: str) -> Skill | None:
    haystack = (text or "").lower()
    for skill in skills:
        if any(trigger and trigger in haystack for trigger in skill.triggers):
            return skill
    return None
