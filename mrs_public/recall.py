"""Turn what was said into canon for this install. The shipped prompt stays unchanged."""

from __future__ import annotations

import json
import os
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


SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}
MAX_TREE = 200


def tree_paths(
    root: Path,
    *,
    install: Path | None = None,
    file_access: bool = False,
    user_root: str = "",
) -> tuple[list[str], int]:
    """Every entry in the whole tree, as paths relative to the root.

    Directories end with "/". Symlinks are not followed. Vendor and
    cache folders are skipped by name. Entries her zones call closed
    are skipped when the install is known. Returns (shown, total):
    shown is capped at MAX_TREE entries; total counts everything the
    walk found, so a capped listing can say so instead of trimming
    silently.
    """
    if not root or not root.exists():
        return [], 0
    base = Path(root)
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        here = Path(dirpath)
        dirnames[:] = sorted(
            (
                name
                for name in dirnames
                if name not in SKIP_DIRS and not (here / name).is_symlink()
            ),
            key=str.lower,
        )
        entries = [(here / name, True) for name in dirnames]
        entries += [
            (here / name, False) for name in sorted(filenames, key=str.lower)
        ]
        for path, is_dir in entries:
            if path.is_symlink():
                continue
            if (
                install is not None
                and zone(
                    path,
                    install,
                    file_access=file_access,
                    user_root=user_root or str(base),
                )
                == "closed"
            ):
                continue
            rel = path.relative_to(base).as_posix()
            found.append(rel + "/" if is_dir else rel)
    found.sort(key=str.lower)
    return found[:MAX_TREE], len(found)


def tree_sentence(shown: list[str], total: int) -> str:
    """The whole tree in one sentence. The count is part of the fact,
    and a capped listing says how much it left out."""
    listing = ", ".join(shown) if shown else "(empty)"
    if total > len(shown):
        return (
            f"{len(shown)} of {total} entries in the whole tree: {listing}. "
            f"({total - len(shown)} more not listed.)"
        )
    word = "entry" if total == 1 else "entries"
    return f"{total} {word} in the whole tree: {listing}."


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
        if folder.is_dir():
            shown, total = tree_paths(
                folder,
                install=install,
                file_access=bool(profile.get("file_access")),
                user_root=str(profile.get("user_root") or ""),
            )
        else:
            shown, total = [], 0
        parts.append(f"Directory already read: {folder}.")
        parts.append(tree_sentence(shown, total))
        parts.append(
            "That is the whole tree, every subfolder. She may read any file in it: "
            "when the user names a file in this tree, its text is fetched and put "
            "in front of her. Outside this tree and her own workspace, the drive "
            "stays closed."
        )
    elif profile.get("file_access"):
        parts.append("Local file access is on. No session directory is set. Ask for one path.")
    else:
        parts.append("Local file access is off. Home directories stay closed until a session path is granted.")
    parts.append("System files, her install, and her program stay closed. She cannot delete herself. A shell is not used. Do not ask for pasted command output.")
    return "\n".join(parts)


def turn_note(work_path: str = "") -> str:
    """Short fact placed beside the latest message so a base model cannot talk over it."""
    if work_path and Path(work_path).is_dir():
        shown, total = tree_paths(Path(work_path))
        return (
            f"Directory already read: {work_path}. "
            + tree_sentence(shown, total)
            + " This is a real listing from this machine, the whole tree. "
            "She may read any file in this tree when the user names it. "
            "Do not say you cannot read files. Do not ask for pasted command output. Do not call this roleplay."
        )
    return (
        "No session directory is set. Ask for one path. "
        "Do not say you cannot read a filesystem. Do not ask for pasted command output."
    )
