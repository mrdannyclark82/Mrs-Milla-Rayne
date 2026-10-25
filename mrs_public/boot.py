"""First boot. Permission, scan, suggest, write the pack, then the intro.

This module does not call `ollama create` and does not open a cloud model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import pack
from .guard import leaks
from .memory import Memory
from .models import is_house, suggest
from .names import INTRO, PRODUCT, SETUP_STEPS, SPEAK_VOLUME
from .scan import Scan, scan_ollama


@dataclass
class BootResult:
    ok: bool
    reason: str
    mode: str = ""
    choices: dict = field(default_factory=dict)
    files: list[str] = field(default_factory=list)
    intro: str = ""
    volume: float = SPEAK_VOLUME
    next_steps: list[str] = field(default_factory=list)


def _check_prompts() -> str:
    texts = [
        pack.read_prompt("companion"),
        pack.read_prompt("code"),
        pack.read_prompt("vision"),
    ]
    found = []
    for text in texts:
        found.extend(leaks(text))
    if found:
        return "Public prompt leaked private words: " + ", ".join(sorted(set(found)))
    return ""


def plan(scan: Scan, *, mode: str, choices: dict | None = None) -> BootResult:
    blocked = _check_prompts()
    if blocked:
        return BootResult(False, blocked)
    if not scan.ok:
        return BootResult(False, scan.reason or "No models to wrap.")
    mode = mode if mode in {"auto", "custom"} else "custom"
    suggested = suggest(list(scan.models))
    picked = dict(suggested)
    if mode == "custom":
        picked.update({k: v for k, v in (choices or {}).items() if v})
    for role in ("companion", "code", "vision", "embed"):
        tag = picked.get(role)
        if tag and is_house(str(tag)):
            return BootResult(False, f"{tag} stays on the house. Pick a different model for {role}.")
    if not picked.get("companion"):
        return BootResult(False, "No public chat model to wrap. House weights are not the default.")
    return BootResult(
        True,
        suggested.get("code_reason") or "",
        mode=mode,
        choices={k: picked.get(k) for k in ("companion", "code", "vision", "embed")},
        intro=INTRO,
        volume=SPEAK_VOLUME,
        next_steps=list(SETUP_STEPS),
    )


def write_install(dest: Path, result: BootResult, *, runtime: str = "ollama", base_url: str = "") -> BootResult:
    if not result.ok:
        return result
    dest = Path(dest)
    persona = dest / "persona"
    state = dest / "state"
    canvas = dest / "canvas"
    voice = dest / "voice"
    workspace = dest / "workspace"
    for path in (persona, state, canvas, voice, workspace):
        path.mkdir(parents=True, exist_ok=True)

    written: list[str] = []
    for role in ("companion", "code", "vision"):
        base = result.choices.get(role)
        if not base:
            continue
        if runtime == "ollama":
            text = pack.ollama_modelfile(role, str(base))
            path = persona / f"{role}.Modelfile"
            path.write_text(text, encoding="utf-8")
        else:
            body = pack.openai_preset(role, str(base), base_url or "http://127.0.0.1:8080/v1")
            path = persona / f"{role}.preset.json"
            path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
        leak = leaks(path.read_text(encoding="utf-8"))
        if leak:
            return BootResult(False, f"Refusing to write {path.name}. Private words: {', '.join(leak)}")
        written.append(str(path))

    profile = {
        "product": PRODUCT,
        "runtime": runtime,
        "choices": result.choices,
        "wrapper_note": "These files dress the chosen weights. They are not a trained model.",
        "sandbox": "off",
        "execute": False,
        "file_access": False,
        "background_review": False,
        "memory": ["canon", "episodes", "reviews"],
        "canvas": "workspace/",
        "workspace": str(workspace),
        "voice": {
            "engine": "xtts",
            "timbre": "custom-milla",
            "volume": result.volume,
            "device": "user",
        },
    }
    (state / "profile.json").write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    (state / "truth_events.jsonl").write_text(
        json.dumps(
            {
                "kind": "canon",
                "id": "install",
                "text": "This truth log started empty for this install.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (state / "neuro_state.json").write_text(
        json.dumps(
            {"dopamine": 0.5, "serotonin": 0.5, "norepinephrine": 0.2, "oxytocin": 0.5}
        )
        + "\n",
        encoding="utf-8",
    )
    (voice / "intro.txt").write_text(result.intro + "\n", encoding="utf-8")
    (workspace / "README.md").write_text(
        "Files she creates land here. Nothing in here is executed.\n"
        "A download zips this directory and leaves the rest of the machine out.\n",
        encoding="utf-8",
    )
    (canvas / "README.md").write_text(
        "Older desk. New files land in the workspace.\n",
        encoding="utf-8",
    )
    Memory(dest)
    written.extend(
        [
            str(state / "profile.json"),
            str(state / "truth_events.jsonl"),
            str(state / "neuro_state.json"),
            str(voice / "intro.txt"),
            str(workspace / "README.md"),
            str(canvas / "README.md"),
        ]
    )
    result.files = written
    return result


def first_boot(
    dest: Path,
    *,
    permission: bool,
    mode: str = "auto",
    host: str = "http://127.0.0.1:11434",
    choices: dict | None = None,
    opener=None,
    runtime: str = "ollama",
    base_url: str = "",
) -> BootResult:
    scan = scan_ollama(host, permission=permission, opener=opener)
    result = plan(scan, mode=mode, choices=choices)
    if not result.ok:
        return result
    return write_install(dest, result, runtime=runtime, base_url=base_url)
