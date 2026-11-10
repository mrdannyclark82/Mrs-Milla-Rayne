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

Traffic to a loopback URL goes through ``open_model``: no proxy from the
environment, and a socket whose peer is not a loopback address is closed
before a byte is written. A reply called local therefore came over a
socket that never left this machine.
"""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse
from urllib.request import HTTPHandler, HTTPSHandler, ProxyHandler, Request, build_opener, urlopen

OLLAMA_URL = "http://127.0.0.1:11434"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def is_loopback_url(url: str) -> bool:
    return (urlparse(url).hostname or "") in LOOPBACK_HOSTS


@dataclass(frozen=True)
class Provider:
    id: str
    kind: str  # "ollama" | "openai"
    url: str
    label: str

    @property
    def local(self) -> bool:
        return is_loopback_url(self.url)


class NotOnThisMachine(OSError):
    """A loopback URL connected to a peer that is not this machine."""


def _loopback_address(raw: str) -> bool:
    try:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
    except ValueError:
        return False
    mapped = getattr(ip, "ipv4_mapped", None)
    return bool(ip.is_loopback or (mapped is not None and mapped.is_loopback))


def _connect_loopback(address, *args, **kwargs) -> socket.socket:
    sock = socket.create_connection(address, *args, **kwargs)
    try:
        peer = str(sock.getpeername()[0])
    except OSError:
        sock.close()
        raise
    if not _loopback_address(peer):
        sock.close()
        raise NotOnThisMachine(f"{address[0]} answered from {peer}, which is not this machine.")
    return sock


class _LoopbackHTTP(http.client.HTTPConnection):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_loopback


class _LoopbackHTTPS(http.client.HTTPSConnection):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._create_connection = _connect_loopback


class _LoopbackHTTPHandler(HTTPHandler):
    def http_open(self, req):  # noqa: ANN001, ANN201
        return self.do_open(_LoopbackHTTP, req)


class _LoopbackHTTPSHandler(HTTPSHandler):
    def https_open(self, req):  # noqa: ANN001, ANN201
        return self.do_open(_LoopbackHTTPS, req, context=self._context)


def open_model(target: Request | str, timeout: float):
    """Open a request to a model server.

    A loopback URL is never handed to an environment proxy, and redirects
    it answers with stay under the same loopback-only socket rule. Other
    hosts keep the ordinary client; their replies are not called local.
    """
    url = target.full_url if isinstance(target, Request) else str(target)
    if not is_loopback_url(url):
        return urlopen(target, timeout=timeout)
    # Built per call: the TLS context reads SSL_CERT_FILE when it is made.
    opener = build_opener(ProxyHandler({}), _LoopbackHTTPHandler(), _LoopbackHTTPSHandler())
    return opener.open(target, timeout=timeout)


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
