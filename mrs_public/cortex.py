"""Public orchestration. Picks a role and whether a tool is needed.

This is not the house prefrontal prompt. It does not see house instructions.
"""

from __future__ import annotations


def choose(
    text: str,
    *,
    has_vision: bool,
    has_embed: bool,
    file_access: bool = False,
) -> dict:
    low = (text or "").lower()
    tools: list[str] = []
    if any(word in low for word in ("image", "photo", "picture", "screenshot")) and has_vision:
        role = "vision"
    elif any(word in low for word in ("code", "function", "bug", "refactor", "compile", "patch")):
        role = "code"
        if file_access:
            tools.append("workspace_read")
    else:
        role = "companion"
    if file_access:
        tools.append("workspace_write")
    else:
        tools.extend(["canvas_write", "download_ready"])
    if has_embed and file_access and any(word in low for word in ("search my files", "find in the notes", "index")):
        tools.append("session_index")
    wants_exec = "run this" in low or low.startswith("sudo") or "exec(" in low
    if file_access:
        reason = "Each file she adds shows up in the workspace. Running it is a separate permission."
    else:
        reason = "The desk holds the work. A download is ready when generation finishes."
    if wants_exec:
        reason = "Running is a separate permission. The canvas still keeps the file."
    return {
        "role": role,
        "tools": tools,
        "sandbox": "off",
        "execute": False,
        "file_access": file_access,
        "reason": reason,
    }
