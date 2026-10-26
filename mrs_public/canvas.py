"""The desk she works on.

File access writes into the workspace and records every addition.
Without it, the work stays on the app desk and can be downloaded when finished.
Neither path runs what she wrote.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .bounds import can_delete, can_write, workspace_root, zone


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_relative(name: str) -> Path:
    raw = (name or "").replace("\\", "/").strip().lstrip("/")
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise ValueError("that path leaves the desk")
    return path


def _inside(root: Path, target: Path) -> None:
    root = root.resolve()
    target = target.resolve()
    if target != root and root not in target.parents:
        raise ValueError("that path leaves the desk")


def place(
    install: Path,
    name: str,
    content: str | bytes,
    *,
    file_access: bool = False,
    workspace: Path | None = None,
) -> dict:
    """Save into her workspace. She has that without a grant.

    file_access does not change this path. Writing into the user's files is separate.
    """
    del file_access, workspace
    rel = safe_relative(name)
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    root = workspace_root(install)
    target = root / rel
    where = "hers"
    download = True
    target.parent.mkdir(parents=True, exist_ok=True)
    if not can_write(target, install):
        raise ValueError("rwx stops at her workspace")
    _inside(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    row = {
        "at": _now(),
        "relative": rel.as_posix(),
        "path": str(target),
        "bytes": len(data),
        "where": where,
        "download": download,
        "executed": False,
    }
    state = Path(install) / "state"
    state.mkdir(parents=True, exist_ok=True)
    with (state / "additions.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return row


def delete_hers(install: Path, name: str) -> dict:
    """Remove one file inside her workspace. Directories, the install, and the system stay."""
    rel = safe_relative(name)
    target = workspace_root(install) / rel
    if not can_delete(target, install):
        raise ValueError("she cannot delete that")
    target.unlink()
    return {"relative": rel.as_posix(), "deleted": True, "where": "hers"}


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return f"(binary file, {len(data)} bytes)"


def read_home(install: Path, name: str, *, user_root: str) -> dict:
    """Read one file in the granted home. Install, program, and system paths stay closed."""
    rel = safe_relative(name)
    target = (Path(user_root) / rel).resolve()
    if zone(target, install, file_access=True, user_root=user_root) != "home" or not target.is_file():
        raise ValueError("that home path is closed")
    return {"relative": rel.as_posix(), "content": _decode(target.read_bytes()), "where": "home"}


def read_under(install: Path, root: Path, name: str, *, user_root: str = "") -> dict:
    """Read one file under a granted root — the session's active workspace.

    The root itself was fenced when it was granted (accept_directory).
    Anything under it that her zones call hers or home may be read, at
    any depth. System paths, her install, and her program stay closed
    even here.
    """
    rel = safe_relative(name)
    base = Path(root).resolve()
    target = (base / rel).resolve()
    if target != base and base not in target.parents:
        raise ValueError("that path leaves the workspace")
    kind = zone(target, install, file_access=True, user_root=user_root or str(base))
    if kind not in {"home", "hers"} or not target.is_file():
        raise ValueError("that path is closed")
    return {"relative": rel.as_posix(), "content": _decode(target.read_bytes()), "where": kind}


def additions(install: Path) -> list[dict]:
    path = Path(install) / "state" / "additions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def download_desk(install: Path) -> Path:
    """Zip the app desk. This does not include the user's home."""
    desk = Path(install) / "workspace"
    has_files = desk.exists() and any(path.is_file() for path in desk.rglob("*"))
    if not has_files:
        legacy = Path(install) / "canvas"
        if legacy.exists() and any(path.is_file() for path in legacy.rglob("*")):
            desk = legacy
    desk.mkdir(parents=True, exist_ok=True)
    out_dir = Path(install) / "state" / "downloads"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = out_dir / f"canvas-{stamp}.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(desk.rglob("*")):
            if path.is_file():
                zipped.write(path, path.relative_to(desk).as_posix())
    return archive
