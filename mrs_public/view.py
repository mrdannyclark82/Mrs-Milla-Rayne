"""Local canvas window. Loopback only. This is the page we keep.

Default install: ~/.mrs-milla-rayne
Open: http://127.0.0.1:8790
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import __version__
from .bounds import accept_directory
from .canvas import additions, download_desk, place, read_home
from .chat import create_session, list_sessions, load_session, save_session, stream_chat, visible_models
from .guard import leaks
from .memory import Memory, PILES
from .models import public_tags, suggest
from .providers import find_provider, load_providers
from .scan import scan_openai
from .names import PRODUCT
from .recall import ensure_roots, learn_history
from .review import on_open

PAGE = Path(__file__).with_name("studio_page.html")
HOST = "127.0.0.1"
PORT = 8790
MAX_BODY = 1_000_000
CHAT_MAX_BODY = 16_000_000  # a chat turn may carry one image (10 MB as base64)


def default_install() -> Path:
    return Path.home() / ".mrs-milla-rayne"


def ensure_install(install: Path) -> Path:
    install = Path(install)
    (install / "canvas").mkdir(parents=True, exist_ok=True)
    workspace = install / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (install / "state").mkdir(parents=True, exist_ok=True)
    Memory(install)
    profile_path = install / "state" / "profile.json"
    if not profile_path.exists():
        profile_path.write_text(
            json.dumps(
                {
                    "product": PRODUCT,
                    "file_access": False,
                    "execute": False,
                    "background_review": False,
                    "canvas": "workspace/",
                    "workspace": str(workspace),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    readme = workspace / "README.md"
    if not readme.exists():
        readme.write_text(
            "Files she creates land here. Nothing here is executed.\n",
            encoding="utf-8",
        )
    text = PAGE.read_text(encoding="utf-8")
    found = leaks(text)
    if found:
        raise RuntimeError("canvas page leaked private words: " + ", ".join(found))
    return install


def load_profile(install: Path) -> dict:
    path = install / "state" / "profile.json"
    if not path.exists():
        data = {}
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("file_access", False)
    data.setdefault("workspace", "")
    data.setdefault("scan_allowed", False)
    data["execute"] = False
    return data


def save_profile(install: Path, profile: dict) -> dict:
    profile["execute"] = False
    path = install / "state" / "profile.json"
    path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return profile


def update_profile(install: Path, patch: dict) -> dict:
    profile = load_profile(install)
    workspace = Path(install) / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    profile["workspace"] = str(workspace)
    if "file_access" in patch:
        profile["file_access"] = bool(patch["file_access"])
        if profile["file_access"] and not profile.get("user_root"):
            profile["user_root"] = str(Path.home())
    if "scan_allowed" in patch:
        profile["scan_allowed"] = bool(patch["scan_allowed"])
    if "providers" in patch:
        profile["providers"] = patch["providers"]
    return save_profile(install, profile)


def desk_files(install: Path) -> list[dict]:
    root = install / "canvas"
    rows = []
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*")):
        if path.is_file():
            rows.append({"relative": path.relative_to(root).as_posix(), "bytes": path.stat().st_size})
    return rows


def read_file(install: Path, rel: str) -> dict:
    from .canvas import safe_relative

    relative = safe_relative(rel)
    target = None
    for root in (install / "workspace", install / "canvas"):
        candidate = (root / relative).resolve()
        root_resolved = root.resolve()
        if candidate != root_resolved and root_resolved not in candidate.parents:
            raise ValueError("that path leaves the desk")
        if candidate.is_file():
            target = candidate
            break
    if target is None:
        raise ValueError("that file is not on her workspace")
    data = target.read_bytes()
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = f"(binary file, {len(data)} bytes)"
    return {"relative": relative.as_posix(), "content": content}


def state(install: Path, scan_opener=None) -> dict:
    profile = ensure_roots(install)
    memory = Memory(install)
    models: list[str] = []
    ollama_ok = not profile.get("scan_allowed")
    ollama_error = ""
    if profile.get("scan_allowed"):
        scan = visible_models("http://127.0.0.1:11434", permission=True, opener=scan_opener)
        models = list(scan.models)
        ollama_ok = scan.ok
        ollama_error = scan.reason
    provider_models: list[dict] = []
    if profile.get("scan_allowed"):
        for provider in load_providers(profile):
            if provider.kind == "ollama":
                continue
            pscan = scan_openai(provider.url, permission=True, opener=scan_opener)
            provider_models.append(
                {
                    "id": provider.id,
                    "label": provider.label,
                    "kind": provider.kind,
                    "url": provider.url,
                    "local": provider.local,
                    "ok": pscan.ok,
                    "error": pscan.reason,
                    "models": list(public_tags(list(pscan.models))) if pscan.ok else [],
                }
            )
    return {
        "product": PRODUCT,
        "version": __version__,
        "file_access": bool(profile.get("file_access")),
        "user_root": profile.get("user_root") or "",
        "user_files": [],
        "her_workspace": profile.get("workspace") or "",
        "execute": False,
        "scan_allowed": bool(profile.get("scan_allowed")),
        "ollama_ok": ollama_ok,
        "ollama_error": ollama_error,
        "models": models,
        "provider_models": provider_models,
        "suggested": (suggest(models).get("companion") if models else "") or "",
        "vision_model": (suggest(models).get("vision") if models else "") or "",
        "sessions": list_sessions(install),
        "additions": additions(install),
        "files": desk_files(install),
        "memory": {name: len(memory.read(name)) for name in PILES},
    }


def make_handler(install: Path, chat_opener=None, scan_opener=None):
    root = Path(install)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, body: bytes, content_type: str, filename: str = "") -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, payload: dict) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

        def _read_json(self, limit: int = MAX_BODY) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length > limit:
                raise ValueError("that file is too large for the desk")
            raw = self.rfile.read(length) if length else b""
            if not raw:
                return {}
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                    return
                if parsed.path == "/api/state":
                    self._json(200, state(root, scan_opener))
                    return
                if parsed.path.startswith("/api/sessions/"):
                    self._json(200, load_session(root, parsed.path.rsplit("/", 1)[-1]))
                    return
                if parsed.path == "/api/home-file":
                    profile = load_profile(root)
                    if not profile.get("file_access") or not profile.get("user_root"):
                        raise ValueError("local file access is off")
                    rel = parse_qs(parsed.query).get("rel", [""])[0]
                    self._json(200, read_home(root, rel, user_root=str(profile["user_root"])))
                    return
                if parsed.path == "/api/file":
                    rel = parse_qs(parsed.query).get("rel", [""])[0]
                    self._json(200, read_file(root, rel))
                    return
                if parsed.path == "/api/download.zip":
                    archive = download_desk(root)
                    self._send(200, archive.read_bytes(), "application/zip", archive.name)
                    return
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            self._json(404, {"error": "not found"})

        def _place(self, body: dict) -> dict:
            profile = load_profile(root)
            workspace = profile.get("workspace") or None
            content = body.get("content") or ""
            if body.get("binary"):
                import base64
                content = base64.b64decode(str(content))
            return place(
                root,
                str(body.get("name") or ""),
                content,
                file_access=bool(profile.get("file_access")),
                workspace=Path(workspace) if workspace else None,
            )

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                body = self._read_json(CHAT_MAX_BODY if parsed.path == "/api/chat" else MAX_BODY)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(400, {"error": str(exc)})
                return
            if parsed.path == "/api/place":
                try:
                    self._json(200, self._place(body))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            if parsed.path == "/api/profile":
                self._json(200, update_profile(root, body))
                return
            if parsed.path == "/api/sessions":
                self._json(200, create_session(root, str(body.get("model") or "")))
                return
            if parsed.path == "/api/session-work":
                try:
                    profile = load_profile(root)
                    session = load_session(root, str(body.get("session_id") or ""))
                    raw = str(body.get("path") or "").strip()
                    if raw:
                        session["work_path"] = str(
                            accept_directory(
                                raw,
                                root,
                                file_access=bool(profile.get("file_access")),
                                user_root=str(profile.get("user_root") or ""),
                            )
                        )
                    else:
                        session.pop("work_path", None)
                    self._json(200, save_session(root, session))
                except ValueError as exc:
                    self._json(400, {"error": str(exc)})
                return
            if parsed.path == "/api/chat":
                self._chat(body)
                return
            self._json(404, {"error": "not found"})

        def _chat(self, body: dict) -> None:
            profile = load_profile(root)
            try:
                provider = None
                provider_id = str(body.get("provider") or "")
                if provider_id and provider_id != "ollama":
                    provider = find_provider(profile, provider_id)
                    if provider is None:
                        raise ValueError(f"Unknown provider: {provider_id}")
                chunks = stream_chat(
                    root,
                    text=str(body.get("text") or ""),
                    model=str(body.get("model") or ""),
                    session_id=str(body.get("session_id") or ""),
                    temperature=float(body.get("temperature") or 0.7),
                    top_p=float(body.get("top_p") or 0.9),
                    use_prompt=bool(body.get("use_prompt", True)),
                    file_access=bool(profile.get("file_access")),
                    image=body.get("image"),
                    scan_opener=scan_opener,
                    opener=chat_opener,
                    provider=provider,
                )
                first = next(chunks)
            except ValueError as exc:
                self._json(400, {"error": str(exc)})
                return
            except Exception as exc:  # noqa: BLE001
                self._json(502, {"error": f"Ollama did not answer. {exc}"})
                return
            self.close_connection = True
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

            def emit(payload: dict) -> None:
                data = (json.dumps(payload) + "\n").encode("utf-8")
                self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")
                self.wfile.flush()

            emit(first)
            for row in chunks:
                emit(row)
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    return Handler


def serve(install: Path, port: int = PORT, chat_opener=None, scan_opener=None) -> ThreadingHTTPServer:
    install = ensure_install(install)
    # Once, when the app opens — not on every state poll: fold past
    # episodes into memory, then run the daily structural review.
    # on_open gates itself to once a day.
    learn_history(install)
    on_open(Memory(install), datetime.now(timezone.utc))
    server = ThreadingHTTPServer((HOST, port), make_handler(install, chat_opener, scan_opener))
    return server


def main(argv: list[str] | None = None) -> None:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    install = Path(args[0]).expanduser() if args else default_install()
    server = serve(install, PORT)
    print(f"Mrs. Milla Rayne at http://{HOST}:{PORT}")
    print(f"Install at {install}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


if __name__ == "__main__":
    main()
