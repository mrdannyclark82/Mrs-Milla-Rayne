"""Where models can live. Ollama is built in; the install may add any
OpenAI-compatible server — llama.cpp, LM Studio, Lemonade — in its
profile, the way the Gradio hub lists its providers.

A provider is just a kind and a base URL:

- ``ollama`` speaks the native Ollama API (``/api/chat``, ``/api/tags``).
- ``openai`` speaks the OpenAI chat API (``/v1/chat/completions``,
  ``/v1/models``) that llama.cpp's server, LM Studio, and Lemonade all
  serve.

Locality is read off the URL, never assumed: a loopback host is on this
machine; anything else is somewhere else, and a reply from it is never
called local.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

OLLAMA_URL = "http://127.0.0.1:11434"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Provider:
    id: str
    kind: str  # "ollama" | "openai"
    url: str
    label: str

    @property
    def local(self) -> bool:
        return (urlparse(self.url).hostname or "") in LOOPBACK_HOSTS


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug or "provider"


def load_providers(profile: dict | None) -> list[Provider]:
    """The built-in Ollama provider, then the install's own list.

    Profile shape: ``"providers": [{"kind": "openai", "url":
    "http://127.0.0.1:8080/v1", "label": "llama.cpp"}, ...]``. An entry
    without a usable kind or URL is skipped, never guessed at. The
    Ollama URL itself can be moved with ``"ollama_url"``.
    """
    profile = profile or {}
    providers = [
        Provider("ollama", "ollama", str(profile.get("ollama_url") or OLLAMA_URL), "Ollama")
    ]
    seen = {"ollama"}
    for raw in profile.get("providers") or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "").strip().lower()
        url = str(raw.get("url") or "").strip()
        if kind not in {"ollama", "openai"} or not url.startswith(("http://", "https://")):
            continue
        label = str(raw.get("label") or ("Ollama" if kind == "ollama" else "OpenAI-compatible")).strip()
        pid = _slug(str(raw.get("id") or label))
        base, n = pid, 2
        while pid in seen:
            pid = f"{base}-{n}"
            n += 1
        seen.add(pid)
        providers.append(Provider(pid, kind, url.rstrip("/"), label))
    return providers


def find_provider(profile: dict | None, provider_id: str | None) -> Provider | None:
    if not provider_id:
        return None
    for provider in load_providers(profile):
        if provider.id == provider_id:
            return provider
    return None
