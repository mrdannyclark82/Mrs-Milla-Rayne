"""Turn what was said into canon for this install. The shipped prompt stays unchanged."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .bounds import zone
from .memory import Memory

NAME_RE = re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z '\-]{0,60})", re.I)


def _profile(install: Path) -> dict:
    path = Path(install) / "state" / "profile.json"
    if not path.exists():
        return {"file_access": False, "execute": False, "workspace": ""}
    data = json.loads(path.read_text(encoding="utf-8"))
    data["execute"] = False
    return data


def _write_profile(install: Path, profile: dict) -> None:
    path = Path(install) / "state" / "profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    profile["execute"] = False
    path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")


def _has(memory: Memory, text: str) -> bool:
    return any(row.get("text") == text for row in memory.read("canon"))


def her_workspace(install: Path) -> Path:
    """Hers without a grant. She cannot keep a workspace she is locked out of."""
    path = Path(install) / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_roots(install: Path) -> dict:
    profile = _profile(install)
    profile["workspace"] = str(her_workspace(install))
    # user_root is set only by the deliberate grant flow (the page toggle),
    # never defaulted to the whole home directory from here. And the
    # profile is rewritten only when something actually changed — this
    # runs on every state poll.
    profile["execute"] = False
    path = Path(install) / "state" / "profile.json"
    text = json.dumps(profile, indent=2) + "\n"
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current != text:
        _write_profile(install, profile)
    return profile


def learn(install: Path, text: str) -> None:
    """Remember a name from what was said. Idempotent.

    File access is NOT learned from sentences. A phrase like "I would
    never grant file access" must not turn it on — the only grant path
    is the deliberate toggle on the page.
    """
    memory = Memory(install)
    found = NAME_RE.search(text or "")
    if found:
        who = re.sub(r"\s+", " ", found.group(1)).strip(" .")
        fact = f"The user's name is {who}."
        if who and not _has(memory, fact):
            memory.add("canon", kind="who", text=fact)


def learn_history(install: Path) -> None:
    for row in Memory(install).read("episodes"):
        learn(install, str(row.get("text") or ""))


def top_names(root: Path, limit: int = 80, *, install: Path | None = None, file_access: bool = False) -> list[str]:
    if not root or not root.exists():
        return []
    names = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.is_symlink():
            continue
        if install is not None and zone(child, install, file_access=file_access, user_root=str(root)) == "closed":
            continue
        names.append(child.name)
        if limit > 0 and len(names) >= limit:
            break
    return names


def ensure_prompt_canon(install: Path) -> None:
    memory = Memory(install)
    fact = "The public prompt is always on."
    if not _has(memory, fact):
        memory.add("canon", kind="canon", text=fact)


def level_sentence(names: list[str]) -> str:
    """Every name at one level. The count is part of the fact."""
    shown = ", ".join(names) if names else "(empty)"
    word = "name" if len(names) == 1 else "names"
    return f"{len(names)} {word} at this one level, all of them: {shown}."


def context_block(install: Path, work_path: str = "") -> str:
    ensure_prompt_canon(install)
    memory = Memory(install)
    profile = ensure_roots(install)
    lines = [str(row.get("text") or "") for row in memory.read("canon") if row.get("text")]
    hers = her_workspace(install)
    parts = ["Operational record for this install. Not a scenario."]
    parts.extend(f"- {line}" for line in lines)
    parts.append(f"Her workspace is always available at {hers}. She has rwx there only.")
    parts.append("Her workspace contains: " + ", ".join(top_names(hers) or ["(empty)"]))
    if work_path:
        folder = Path(work_path)
        names = top_names(folder, limit=0) if folder.is_dir() else []
        parts.append(f"Directory already read: {folder}.")
        parts.append(level_sentence(names))
        parts.append("Not the contents inside those entries.")
        parts.append("That listing is from this machine. Use it. Do not scan the rest of the drive.")
    elif profile.get("file_access"):
        parts.append("Local file access is on. No session directory is set. Ask for one path.")
    else:
        parts.append("Local file access is off. Home directories stay closed until a session path is granted.")
    parts.append("System files, her install, and her program stay closed. She cannot delete herself. A shell is not used. Do not ask for pasted command output.")
    return "\n".join(parts)


def turn_note(work_path: str = "") -> str:
    """Short fact placed beside the latest message so a base model cannot talk over it."""
    if work_path and Path(work_path).is_dir():
        names = top_names(Path(work_path), limit=0)
        return (
            f"Directory already read: {work_path}. "
            + level_sentence(names)
            + " Not the contents inside those entries. "
            "This is a real listing from this machine. "
            "Do not say you cannot read files. Do not ask for pasted command output. Do not call this roleplay."
        )
    return (
        "No session directory is set. Ask for one path. "
        "Do not say you cannot read a filesystem. Do not ask for pasted command output."
    )
