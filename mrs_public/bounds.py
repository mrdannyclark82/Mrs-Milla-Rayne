"""Where she may read, write, and delete.

rwx is her workspace only. Granted home access is read-only.
System paths, her install, and her program stay closed. She cannot delete herself.
"""

from __future__ import annotations

from pathlib import Path

SYSTEM_ROOTS = (
    Path("/bin"),
    Path("/boot"),
    Path("/dev"),
    Path("/etc"),
    Path("/lib"),
    Path("/lib64"),
    Path("/opt"),
    Path("/proc"),
    Path("/root"),
    Path("/run"),
    Path("/sbin"),
    Path("/sys"),
    Path("/usr"),
    Path("/var"),
)


def app_root() -> Path:
    return Path(__file__).resolve().parents[1]


def workspace_root(install: Path) -> Path:
    path = Path(install) / "workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path.resolve()


def _under(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def zone(path: Path, install: Path, *, file_access: bool, user_root: str = "") -> str:
    """Return hers, home, or closed. Symlinks are judged after resolve."""
    resolved = Path(path).resolve()
    for root in SYSTEM_ROOTS:
        if _under(resolved, root):
            return "closed"
    program = app_root().resolve()
    if _under(resolved, program):
        return "closed"
    install_root = Path(install).resolve()
    hers = workspace_root(install)
    if _under(resolved, hers):
        return "hers"
    if _under(resolved, install_root):
        return "closed"
    if file_access and user_root:
        home = Path(user_root).resolve()
        if _under(resolved, home):
            return "home"
    return "closed"


def accept_directory(path: str, install: Path, *, file_access: bool, user_root: str = "") -> Path:
    """A session directory is a path she was given. She does not search for it."""
    if not str(path or "").strip():
        raise ValueError("give her a directory path")
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError("that path is not a directory")
    kind = zone(resolved, install, file_access=file_access, user_root=user_root)
    if kind not in {"home", "hers"}:
        raise ValueError("that directory is closed")
    return resolved


def grant_directory(path: str, install: Path, profile: dict) -> dict:
    """Accept a session directory and record the file-access grant it was accepted under."""
    resolved = accept_directory(
        path,
        install,
        file_access=bool(profile.get("file_access")),
        user_root=str(profile.get("user_root") or ""),
    )
    return {"work_path": str(resolved), "work_grant": str(profile.get("grant") or "")}


def granted_directory(session: dict, install: Path, profile: dict) -> Path | None:
    """The session directory, if this profile still allows it; otherwise None.

    A home directory holds only while file access is on under the same
    grant it was accepted in. Turning access off, or off and on again,
    closes it. Her own workspace needs no grant.
    """
    raw = str(session.get("work_path") or "")
    if not raw:
        return None
    stored = Path(raw)
    try:
        resolved = stored.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if resolved != stored or not resolved.is_dir():
        return None
    kind = zone(
        resolved,
        install,
        file_access=bool(profile.get("file_access")),
        user_root=str(profile.get("user_root") or ""),
    )
    if kind == "hers":
        return resolved
    if kind == "home" and str(session.get("work_grant") or "") == str(profile.get("grant") or ""):
        return resolved
    return None


def can_read(path: Path, install: Path, *, file_access: bool, user_root: str = "") -> bool:
    return zone(path, install, file_access=file_access, user_root=user_root) in {"hers", "home"}


def can_write(path: Path, install: Path) -> bool:
    resolved = Path(path).resolve()
    hers = workspace_root(install)
    return resolved != hers and zone(resolved, install, file_access=False) == "hers"


def can_delete(path: Path, install: Path) -> bool:
    resolved = Path(path).resolve()
    if not resolved.exists() or resolved.is_dir():
        return False
    return can_write(resolved, install)
