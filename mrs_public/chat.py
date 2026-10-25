"""Public chat on the user's model. Never the house kernel."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator
from urllib.request import Request, urlopen

from .bounds import accept_directory
from .cortex import choose
from .memory import Memory
from .models import is_house, public_tags
from .pack import read_prompt, sampler
from .recall import context_block, ensure_roots, learn, turn_note
from .lookup import Resolver, fence, fetch_page, search_web
from .lookup import enabled as web_enabled
from .scan import Scan, scan_ollama

WORK_RE = re.compile(r"\bwork in\s+(\S+)", re.I)
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
LOOKUP_RE = re.compile(r"\b(?:look up|look it up|search the web|search online|web search|google)\b", re.I)
READ_RE = re.compile(r"\b(?:read|open|fetch|summari[sz]e|check)\b", re.I)


def _web_intent(text: str) -> tuple[str, str] | None:
    """('url', address) or ('search', words) when the user asks her to look.

    A pasted address alone is not an ask; an address plus a reading word
    is. Search triggers name the web on purpose — plain talk never fires it.
    """
    raw = (text or "").strip()
    found = URL_RE.search(raw)
    trigger = LOOKUP_RE.search(raw)
    if found and (trigger or READ_RE.search(raw)):
        return "url", found.group(0).rstrip(".,")
    if trigger:
        words = LOOKUP_RE.sub(" ", raw, count=1)
        words = re.sub(r"^\s*(for|about|on|:|-)\s+", " ", words).strip(" :,-")
        words = " ".join(words.split())
        if words:
            return "search", words
    return None


def _web_block(
    intent: tuple[str, str],
    *,
    opener: Callable | None,
    resolver: Resolver | None,
) -> tuple[str, dict]:
    """Run one fenced lookup. Failure becomes a plain sentence, not a crash."""
    kind, target = intent
    try:
        if kind == "url":
            page = fetch_page(target, opener=opener, resolver=resolver)
            body = f"{page.title}\n{page.text}" if page.title else page.text
            return fence(page.url, body), {"lookup": {"kind": "page", "url": page.url, "ok": True}}
        results = search_web(target, opener=opener, resolver=resolver)
        if not results:
            note = (
                f"A web search for \"{target}\" ran just now and returned no readable results. "
                "Say so plainly. Do not invent results."
            )
            return note, {"lookup": {"kind": "search", "query": target, "ok": False}}
        page = fetch_page(results[0].url, opener=opener, resolver=resolver)
        listing = "\n".join(
            f"- {row.title} — {row.url}" + (f"\n  {row.snippet}" if row.snippet else "")
            for row in results
        )
        body = (
            f"Search results for \"{target}\":\n{listing}\n\n"
            f"Top result page, {page.url}:\n{page.title}\n{page.text}"
        )
        return fence(f"a web search for \"{target}\"", body), {
            "lookup": {"kind": "search", "query": target, "url": page.url, "ok": True}
        }
    except Exception as exc:  # noqa: BLE001 — a failed lookup is a sentence, not a crash
        note = (
            f"A web lookup was attempted just now and did not work ({type(exc).__name__}: {exc}). "
            "Say so plainly. Do not invent what the page or the results said."
        )
        event = {"lookup": {"kind": kind, "ok": False}}
        if kind == "search":
            event["lookup"]["query"] = target
        return note, event


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sessions_dir(install: Path) -> Path:
    path = Path(install) / "state" / "sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_sessions(install: Path) -> list[dict]:
    rows = []
    paths = sorted(sessions_dir(install).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            last = data["messages"][-1]["content"][:80] if data.get("messages") else "Empty"
            rows.append({"id": data["id"], "title": data.get("title") or "New session", "preview": last, "model": data.get("model") or ""})
        except (OSError, ValueError, KeyError, TypeError):
            continue  # one unreadable session file must not brick the list
    return rows


def load_session(install: Path, session_id: str) -> dict:
    if not session_id.isalnum():
        raise ValueError("that session is not here")
    path = sessions_dir(install) / f"{session_id}.json"
    if not path.is_file():
        raise ValueError("that session is not here")
    return json.loads(path.read_text(encoding="utf-8"))


def save_session(install: Path, data: dict) -> dict:
    path = sessions_dir(install) / f"{data['id']}.json"
    tmp = path.with_name(f".{data['id']}.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # a crash mid-write leaves the old session, not a torn one
    return data


def create_session(install: Path, model: str) -> dict:
    data = {
        "id": uuid.uuid4().hex[:12],
        "title": "New session",
        "model": model,
        "messages": [],
        "created": _now(),
    }
    return save_session(install, data)


def visible_models(host: str, *, permission: bool, opener: Callable | None = None) -> Scan:
    scan = scan_ollama(host, permission=permission, opener=opener)
    if not scan.ok:
        return scan
    return Scan(True, "ollama", tuple(public_tags(list(scan.models))), "")


def _system(text: str, *, file_access: bool) -> tuple[str, str]:
    choice = choose(text, has_vision=False, has_embed=False, file_access=file_access)
    role = choice["role"] if choice["role"] in {"companion", "code", "vision"} else "companion"
    return role, read_prompt(role)


def iter_ollama(host: str, payload: dict, opener: Callable | None) -> Iterator[str]:
    fetch = opener or urlopen
    req = Request(
        host.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with fetch(req, timeout=180) as resp:
        while True:
            line = resp.readline()
            if not line:
                break
            raw = line.decode("utf-8") if isinstance(line, bytes) else line
            if not raw.strip():
                continue
            chunk = json.loads(raw)
            token = ((chunk.get("message") or {}).get("content")) or ""
            if token:
                yield token
            if chunk.get("done"):
                break


def stream_chat(
    install: Path,
    *,
    text: str,
    model: str,
    session_id: str = "",
    temperature: float = 0.7,
    top_p: float = 0.9,
    use_prompt: bool = True,
    file_access: bool = False,
    host: str = "http://127.0.0.1:11434",
    opener: Callable | None = None,
    web_opener: Callable | None = None,
    web_resolver: Resolver | None = None,
) -> Iterator[dict]:
    if not model:
        raise ValueError("Pick a model from the list.")
    if is_house(model):
        raise ValueError(f"{model} stays on the house. Pick a model from this list.")
    del use_prompt
    learn(install, text)
    profile = ensure_roots(install)
    session = load_session(install, session_id) if session_id else create_session(install, model)
    asked = WORK_RE.search(text or "")
    if asked:
        session["work_path"] = str(
            accept_directory(
                asked.group(1).rstrip(".,)"),
                install,
                file_access=bool(profile.get("file_access")),
                user_root=str(profile.get("user_root") or ""),
            )
        )
    role, system = _system(text, file_access=bool(profile.get("file_access")))
    web_event: dict | None = None
    web_note = ""
    if web_enabled(profile):
        intent = _web_intent(text)
        if intent:
            web_note, web_event = _web_block(intent, opener=web_opener, resolver=web_resolver)
    extra = context_block(install, work_path=session.get("work_path") or "")
    if extra:
        system = f"{system}\n\n{extra}".strip() if system else extra
    session["messages"].append({"role": "user", "content": text, "at": _now()})
    if session.get("title") in {"", "New session"}:
        session["title"] = text.strip()[:48] or "New session"
    outbound = []
    if system:
        outbound.append({"role": "system", "content": system})
    history = [{"role": item["role"], "content": item["content"]} for item in session["messages"]]
    note = {"role": "system", "content": turn_note(session.get("work_path") or "")}
    if history and history[-1]["role"] == "user":
        outbound.extend(history[:-1])
        outbound.append(note)
        if web_note:
            outbound.append({"role": "system", "content": web_note})
        outbound.append(history[-1])
    else:
        outbound.extend(history)
        outbound.append(note)
        if web_note:
            outbound.append({"role": "system", "content": web_note})
    # The persona pack's sampler carries num_ctx and the role defaults;
    # the sliders the user set win for temperature and top_p.
    options = dict(sampler(role))
    options["temperature"] = temperature
    options["top_p"] = top_p
    payload = {
        "model": model,
        "messages": outbound,
        "stream": True,
        "options": options,
    }
    parts: list[str] = []
    if web_event:
        yield web_event
    try:
        for token in iter_ollama(host, payload, opener):
            parts.append(token)
            yield {"token": token}
    except Exception as exc:  # noqa: BLE001 — the page has to say Ollama failed
        yield {"error": f"Ollama did not answer. {type(exc).__name__}: {exc}"}
        return
    reply = "".join(parts)
    session["messages"].append({"role": "assistant", "content": reply, "at": _now(), "role_name": role})
    session["model"] = model
    save_session(install, session)
    Memory(install).add("episodes", text=text, outcome="said", session=session["id"], role=role)
    yield {"done": True, "session": session, "role": role}
