"""Write a persona pack. Ollama gets a Modelfile. Other local servers get a preset."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PERSONA = ROOT / "persona"


def read_prompt(role: str) -> str:
    """The daily-driver spine ships with every speaking role."""
    if role == "embed":
        return ""
    spine = (PERSONA / "public_mrs.md").read_text(encoding="utf-8").strip()
    if role == "companion":
        return spine
    extra = (PERSONA / "roles" / f"{role}.md").read_text(encoding="utf-8").strip()
    return f"{spine}\n\n{extra}"


def sampler(role: str) -> dict:
    data = json.loads((PERSONA / "sampler.json").read_text(encoding="utf-8"))
    return dict(data[role])


def ollama_modelfile(role: str, base: str) -> str:
    """Costume on the user's weights. Not a fine-tune."""
    prompt = read_prompt(role)
    params = sampler(role)
    lines = [
        f"FROM {base}",
        f"PARAMETER temperature {params['temperature']}",
        f"PARAMETER top_p {params['top_p']}",
        f"PARAMETER num_ctx {params['num_ctx']}",
    ]
    if prompt:
        lines.append('SYSTEM """')
        lines.append(prompt)
        lines.append('"""')
    return "\n".join(lines) + "\n"


def openai_preset(role: str, base: str, base_url: str) -> dict:
    """What LM Studio and llama.cpp can apply. This is not an Ollama Modelfile."""
    return {
        "format": "openai-local-preset",
        "role": role,
        "model": base,
        "base_url": base_url,
        "system": read_prompt(role),
        "sampler": sampler(role),
        "note": "Apply system and sampler on this server. Do not pass this file to ollama create.",
    }
