"""Loopback model traffic must not follow the process HTTP proxy.

The default chat client is urllib.request.urlopen. That opener installs
ProxyHandler from http_proxy / https_proxy and does not treat loopback as
a bypass on its own. These tests speak to a loopback model through that
client, with a proxy listening and with no_proxy unset. They fail while
the proxy receives the turn. They pass once the turn is delivered to the
loopback socket, the proxy receives nothing, and the on-machine flag
agrees with that socket.

The page caption is the branch in mrs_public/studio_page.html that reads
row.local. It is executed as that source, not reimplemented.

Left untested, on purpose:
- mrs_public/lookup.py fetches. A loopback target is refused before any
  request, and a public fetch is allowed to use a proxy.
- Link-local and other non-loopback hosts. Provider.local is false for
  them, so the page does not call those replies on-machine.
- mrs_public/boot.py first_boot. It calls scan_ollama, which is tested.
"""

from __future__ import annotations

import http.client
import http.server
import importlib
import ipaddress
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from pathlib import Path

import urllib.request

from mrs_public.memory import Memory
from mrs_public.providers import Provider

PAGE = Path(__file__).resolve().parents[1] / "mrs_public" / "studio_page.html"
PERSONA = Path(__file__).resolve().parents[1] / "persona" / "public_mrs.md"
PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAwMCAO+ip1sAAAAASUVORK5CYII="

ENV_KEYS = (
    "http_proxy",
    "HTTP_PROXY",
    "https_proxy",
    "HTTPS_PROXY",
    "no_proxy",
    "NO_PROXY",
    "all_proxy",
    "ALL_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "REQUEST_METHOD",
)

OLLAMA_REPLY = b'{"message":{"content":"pong"},"done":true}\n'
OPENAI_REPLY = (
    b'data: {"choices":[{"delta":{"content":"pong"}}]}\n\n'
    b"data: [DONE]\n\n"
)
TAGS_REPLY = b'{"models":[{"name":"gemma2:2b"},{"name":"moondream:latest"}]}'
MODELS_REPLY = b'{"data":[{"id":"local-gguf"}]}'


class _ReuseServer(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class _V6Server(_ReuseServer):
    address_family = socket.AF_INET6


class _OriginHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        return

    def _take(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        with self.server.hit_lock:
            self.server.hits.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "body": body,
                    "peer": self.client_address[0],
                }
            )
        return body

    def _send(self, payload: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        self._take()
        path = self.path.split("?", 1)[0].rstrip("/")
        if path.endswith("/api/tags"):
            self._send(TAGS_REPLY, "application/json")
            return
        if path.endswith("/models"):
            self._send(MODELS_REPLY, "application/json")
            return
        self.send_error(404)

    def do_POST(self) -> None:
        self._take()
        path = self.path.split("?", 1)[0].rstrip("/")
        if path.endswith("/chat/completions"):
            self._send(OPENAI_REPLY, "text/event-stream")
            return
        if path.endswith("/api/chat"):
            self._send(OLLAMA_REPLY, "application/x-ndjson")
            return
        self.send_error(404)


class _Proxy:
    """An HTTP proxy that records what it is given and never dials onward.

    A successful HTTP response is returned so a proxied chat can finish.
    CONNECT is refused. The body is therefore only visible when the client
    sent it in cleartext, which is the HTTP loopback case.
    """

    def __init__(self) -> None:
        self.hits: list[dict] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(32)
        self._sock.settimeout(0.2)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._accept, daemon=True)
        self._thread.start()

    def _accept(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(3)
        try:
            data = b""
            while b"\r\n\r\n" not in data and len(data) < 2_000_000:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            head, _, rest = data.partition(b"\r\n\r\n")
            match = None
            for line in head.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    match = line.split(b":", 1)[1].strip()
                    break
            need = int(match) if match else 0
            while len(rest) < need:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                rest += chunk
            body = rest[:need]
            request = head.split(b"\r\n", 1)[0]
            with self._lock:
                self.hits.append({"request": request, "head": head, "body": body})
            conn.sendall(self._reply(request))
        except OSError:
            pass
        finally:
            conn.close()

    def _reply(self, request: bytes) -> bytes:
        line = request.decode("latin1", "replace")
        if line.startswith("CONNECT "):
            return b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        target = line.split(" ")[1] if " " in line else ""
        path = target.split("?", 1)[0].rstrip("/")
        if path.endswith("/api/tags"):
            payload, ctype = TAGS_REPLY, b"application/json"
        elif path.endswith("/models"):
            payload, ctype = MODELS_REPLY, b"application/json"
        elif path.endswith("/chat/completions"):
            payload, ctype = OPENAI_REPLY, b"text/event-stream"
        else:
            payload, ctype = OLLAMA_REPLY, b"application/x-ndjson"
        return (
            b"HTTP/1.1 200 OK\r\nContent-Type: "
            + ctype
            + b"\r\nContent-Length: "
            + str(len(payload)).encode("ascii")
            + b"\r\nConnection: close\r\n\r\n"
            + payload
        )

    def blob(self) -> bytes:
        with self._lock:
            hits = list(self.hits)
        return b"\n".join(hit["head"] + b"\n" + hit["body"] for hit in hits)

    def close(self) -> None:
        self._stop.set()
        try:
            self._sock.close()
        except OSError:
            pass
        self._thread.join(timeout=2)


def _page_caption(*, row: dict, lookup: bool, selected: str) -> str:
    """Run the page's done-row handling and caption branch from the HTML."""
    node = shutil.which("node")
    if not node:
        raise AssertionError("node is required to execute studio_page.html")
    script = r"""
const fs = require("fs");
const html = fs.readFileSync(process.argv[2], "utf8");
const doneAt = html.indexOf("if (row.done)");
const open = html.indexOf("{", doneAt);
const close = html.indexOf("}", open);
const start = html.indexOf('const onCloud = ($("model").value');
const end = html.indexOf("refresh();", start);
if (doneAt < 0 || open < 0 || close < 0 || start < 0 || end < 0) {
  process.stderr.write("caption block missing\n");
  process.exit(2);
}
const args = JSON.parse(process.argv[3]);
const row = args.row;
const state = {};
let usedVision = false;
let usedModel = "";
let usedLocal = true;
let usedProvider = "";
let usedSkill = "";
let usedLookup = !!args.lookup;
eval(html.slice(open + 1, close));
const els = {
  model: { value: args.selected },
  fine: { textContent: "" },
  tps: { textContent: "" },
};
const $ = (id) => {
  if (!Object.prototype.hasOwnProperty.call(els, id)) {
    throw new Error("unknown element " + id);
  }
  return els[id];
};
let acc = "pong";
let started = 0;
const performance = { now: () => 1000 };
eval(html.slice(start, end));
process.stdout.write(els.fine.textContent);
"""
    payload = json.dumps({"row": row, "lookup": lookup, "selected": selected})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "caption.js"
        path.write_text(script, encoding="utf-8")
        run = subprocess.run(
            [node, str(path), str(PAGE), payload],
            check=False,
            capture_output=True,
            text=True,
        )
    if run.returncode != 0:
        raise AssertionError(run.stderr or run.stdout)
    return run.stdout


def _clients():
    """Reload after the proxy env is set so an import-time snapshot sees it."""
    urllib.request._opener = None
    chat = importlib.reload(importlib.import_module("mrs_public.chat"))
    scan = importlib.reload(importlib.import_module("mrs_public.scan"))
    view = importlib.reload(importlib.import_module("mrs_public.view"))
    urllib.request._opener = None
    return chat, scan, view


class LoopbackProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in ENV_KEYS}
        self._dirs: list[tempfile.TemporaryDirectory] = []
        self.addCleanup(self._restore_env)
        self.addCleanup(self._cleanup_dirs)

    def _restore_env(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        urllib.request._opener = None

    def _cleanup_dirs(self) -> None:
        for directory in self._dirs:
            directory.cleanup()

    def _install(self):
        directory = tempfile.TemporaryDirectory()
        self._dirs.append(directory)
        _chat, _scan, view = _clients()
        return view.ensure_install(Path(directory.name)), view

    def _arm_proxy(self, proxy: _Proxy, *, https: bool, cafile: str | None = None) -> None:
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        url = f"http://127.0.0.1:{proxy.port}"
        os.environ["http_proxy"] = url
        os.environ["HTTP_PROXY"] = url
        if https:
            os.environ["https_proxy"] = url
            os.environ["HTTPS_PROXY"] = url
        if cafile:
            os.environ["SSL_CERT_FILE"] = cafile
        urllib.request._opener = None

    @contextmanager
    def _origin(self, host: str, port: int = 0, *, tls: ssl.SSLContext | None = None):
        server_cls = _V6Server if host == "::1" else _ReuseServer

        class Server(server_cls):
            def get_request(self):
                conn, addr = super().get_request()
                if tls is None:
                    return conn, addr
                try:
                    return tls.wrap_socket(conn, server_side=True), addr
                except ssl.SSLError:
                    conn.close()
                    raise

        server = Server((host, port), _OriginHandler)
        server.hits = []
        server.hit_lock = threading.Lock()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def _leak(self, proxy: _Proxy, rows: list[dict]) -> str:
        local = None
        for row in rows:
            if row.get("done"):
                local = row.get("local")
        shown = proxy.blob()[:600].decode("utf-8", "replace")
        return f"proxy received {len(proxy.hits)} request(s); done.local={local!r}; first bytes: {shown!r}"

    def _assert_direct(self, proxy: _Proxy, origin, rows: list[dict], markers: list[str], *, caption: str, selected: str) -> None:
        self.assertEqual(proxy.hits, [], self._leak(proxy, rows))
        with origin.hit_lock:
            hits = list(origin.hits)
        posts = [hit for hit in hits if hit["method"] == "POST"]
        self.assertTrue(posts, f"loopback server saw no POST: {hits!r}")
        body = b"\n".join(hit["body"] for hit in posts)
        missing = [marker for marker in markers if marker.encode("utf-8") not in body]
        self.assertEqual(missing, [], body[:800])
        peers = [hit["peer"] for hit in posts]
        self.assertTrue(peers)
        for peer in peers:
            self.assertTrue(ipaddress.ip_address(peer).is_loopback, peer)
        done = rows[-1]
        self.assertTrue(done.get("done"), rows)
        # The flag has to describe the socket that got the body. A URL that
        # merely says loopback is not enough: the proxy also sits on loopback.
        self.assertIs(done["local"], True)
        text = _page_caption(
            row=done,
            lookup=any(bool(row.get("lookup")) for row in rows),
            selected=selected,
        )
        self.assertEqual(text, caption)

    def _prepare_turn(self, install: Path, chat) -> tuple[str, str, list[str]]:
        persona = PERSONA.read_text(encoding="utf-8").splitlines()[0]
        canon = "CANON_MARKER_the user keeps the blue notebook"
        Memory(install).add("canon", kind="who", text=canon)
        work = install / "workspace"
        file_text = "FILE_MARKER_quarterly figures stay in this file"
        (work / "secret.txt").write_text(file_text, encoding="utf-8")
        transcript = "TRANSCRIPT_MARKER_earlier the user said the door code"
        session = chat.create_session(install, "gemma2:2b")
        session["messages"] = [
            {"role": "user", "content": transcript, "at": "2026-01-01T00:00:00+00:00"},
            {"role": "assistant", "content": "noted", "at": "2026-01-01T00:00:01+00:00"},
        ]
        chat.save_session(install, session)
        ask = f"work in {work} read secret.txt and remember ASK_MARKER_today"
        return session["id"], ask, [persona, canon, file_text, transcript, "ASK_MARKER_today"]

    def test_default_ollama_chat_stays_on_the_loopback_socket(self) -> None:
        proxy = _Proxy()
        self.addCleanup(proxy.close)
        self._arm_proxy(proxy, https=True)
        chat, _scan, _view = _clients()
        install, _view = self._install()
        session_id, ask, markers = self._prepare_turn(install, chat)
        with self._origin("127.0.0.1", 11434) as origin:
            rows = list(
                chat.stream_chat(
                    install,
                    text=ask,
                    model="gemma2:2b",
                    session_id=session_id,
                )
            )
        self._assert_direct(
            proxy,
            origin,
            rows,
            markers,
            caption="Reply stayed on this machine.",
            selected="gemma2:2b",
        )

    def test_localhost_and_ipv6_ollama_chats_stay_on_the_loopback_socket(self) -> None:
        cases = (
            ("localhost", "::1", "http://localhost:{port}"),
            ("::1", "::1", "http://[::1]:{port}"),
        )
        for name, bind, template in cases:
            with self.subTest(host=name):
                proxy = _Proxy()
                self.addCleanup(proxy.close)
                self._arm_proxy(proxy, https=False)
                chat, _scan, _view = _clients()
                install, _view = self._install()
                marker = f"ASK_MARKER_{name}"
                with self._origin(bind) as origin:
                    port = origin.server_address[1]
                    rows = list(
                        chat.stream_chat(
                            install,
                            text=marker,
                            model="gemma2:2b",
                            host=template.format(port=port),
                        )
                    )
                self._assert_direct(
                    proxy,
                    origin,
                    rows,
                    [marker, PERSONA.read_text(encoding="utf-8").splitlines()[0]],
                    caption="Reply stayed on this machine.",
                    selected="gemma2:2b",
                )

    def test_openai_loopback_chats_stay_on_the_loopback_socket(self) -> None:
        cases = (
            ("127.0.0.1", "127.0.0.1", "http://127.0.0.1:{port}/v1"),
            ("localhost", "::1", "http://localhost:{port}/v1"),
            ("::1", "::1", "http://[::1]:{port}/v1"),
        )
        for name, bind, template in cases:
            with self.subTest(host=name):
                proxy = _Proxy()
                self.addCleanup(proxy.close)
                self._arm_proxy(proxy, https=False)
                chat, _scan, _view = _clients()
                install, _view = self._install()
                marker = f"ASK_MARKER_openai_{name}"
                with self._origin(bind) as origin:
                    port = origin.server_address[1]
                    url = template.format(port=port)
                    provider = Provider("local-box", "openai", url, "llama.cpp")
                    self.assertTrue(provider.local)
                    rows = list(
                        chat.stream_chat(
                            install,
                            text=marker,
                            model="local-gguf",
                            provider=provider,
                        )
                    )
                self._assert_direct(
                    proxy,
                    origin,
                    rows,
                    [marker],
                    caption="Reply stayed on this machine.",
                    selected="local-gguf",
                )
                self.assertTrue(any(hit["path"].endswith("/chat/completions") for hit in origin.hits))

    def test_https_loopback_openai_chat_is_not_tunneled(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self._dirs.append(directory)
        root = Path(directory.name)
        cert = root / "cert.pem"
        key = root / "key.pem"
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-keyout",
                str(key),
                "-out",
                str(cert),
                "-days",
                "1",
                "-subj",
                "/CN=127.0.0.1",
                "-addext",
                "subjectAltName=IP:127.0.0.1,DNS:localhost",
            ],
            check=True,
            capture_output=True,
        )
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        proxy = _Proxy()
        self.addCleanup(proxy.close)
        self._arm_proxy(proxy, https=True, cafile=str(cert))
        chat, _scan, _view = _clients()
        install, _view = self._install()
        marker = "ASK_MARKER_https_loopback"
        with self._origin("127.0.0.1", tls=ctx) as origin:
            port = origin.server_address[1]
            url = f"https://127.0.0.1:{port}/v1"
            provider = Provider("local-tls", "openai", url, "llama.cpp")
            self.assertTrue(provider.local)
            rows = list(
                chat.stream_chat(
                    install,
                    text=marker,
                    model="local-gguf",
                    provider=provider,
                )
            )
        self._assert_direct(
            proxy,
            origin,
            rows,
            [marker],
            caption="Reply stayed on this machine.",
            selected="local-gguf",
        )

    def test_image_bytes_reach_the_loopback_socket_only(self) -> None:
        proxy = _Proxy()
        self.addCleanup(proxy.close)
        self._arm_proxy(proxy, https=False)
        chat, _scan, _view = _clients()
        install, _view = self._install()
        with self._origin("127.0.0.1") as origin:
            port = origin.server_address[1]
            rows = list(
                chat.stream_chat(
                    install,
                    text="What is in this picture?",
                    model="gemma2:2b",
                    host=f"http://127.0.0.1:{port}",
                    image={"type": "image/png", "data": PNG_1PX},
                )
            )
        self._assert_direct(
            proxy,
            origin,
            rows,
            [PNG_1PX],
            caption="Reply stayed on this machine. The local vision model (moondream:latest) did the looking.",
            selected="gemma2:2b",
        )

    def test_model_scans_stay_on_the_loopback_socket(self) -> None:
        proxy = _Proxy()
        self.addCleanup(proxy.close)
        self._arm_proxy(proxy, https=False)
        _chat, scan, _view = _clients()
        with self._origin("127.0.0.1") as ollama, self._origin("127.0.0.1") as openai:
            ollama_port = ollama.server_address[1]
            openai_port = openai.server_address[1]
            ollama_scan = scan.scan_ollama(f"http://127.0.0.1:{ollama_port}", permission=True)
            openai_scan = scan.scan_openai(f"http://127.0.0.1:{openai_port}/v1", permission=True)
        self.assertEqual(proxy.hits, [], self._leak(proxy, []))
        self.assertTrue(ollama_scan.ok, ollama_scan.reason)
        self.assertIn("gemma2:2b", ollama_scan.models)
        self.assertTrue(openai_scan.ok, openai_scan.reason)
        self.assertIn("local-gguf", openai_scan.models)
        with ollama.hit_lock:
            ollama_hits = list(ollama.hits)
        with openai.hit_lock:
            openai_hits = list(openai.hits)
        self.assertTrue(any(hit["path"].endswith("/api/tags") for hit in ollama_hits))
        self.assertTrue(any(hit["path"].endswith("/models") for hit in openai_hits))
        for hit in ollama_hits + openai_hits:
            self.assertTrue(ipaddress.ip_address(hit["peer"]).is_loopback)

    def test_state_poll_uses_the_loopback_socket(self) -> None:
        proxy = _Proxy()
        self.addCleanup(proxy.close)
        self._arm_proxy(proxy, https=False)
        _chat, _scan, view = _clients()
        install, view = self._install()
        with self._origin("127.0.0.1", 11434) as ollama, self._origin("127.0.0.1") as openai:
            port = openai.server_address[1]
            profile_path = install / "state" / "profile.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            profile["scan_allowed"] = True
            profile["providers"] = [
                {"kind": "openai", "url": f"http://127.0.0.1:{port}/v1", "label": "llama.cpp"}
            ]
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            # state() closes over the reloaded scan functions via view.
            snapshot = view.state(install)
        self.assertEqual(proxy.hits, [], self._leak(proxy, []))
        self.assertIn("gemma2:2b", snapshot["models"])
        self.assertEqual(snapshot["provider_models"][0]["models"], ["local-gguf"])
        self.assertTrue(snapshot["provider_models"][0]["local"])
        with ollama.hit_lock:
            self.assertTrue(ollama.hits)
        with openai.hit_lock:
            self.assertTrue(openai.hits)

    def test_page_chat_post_stays_on_the_loopback_socket(self) -> None:
        proxy = _Proxy()
        self.addCleanup(proxy.close)
        self._arm_proxy(proxy, https=True)
        chat, _scan, view = _clients()
        install, view = self._install()
        session_id, ask, markers = self._prepare_turn(install, chat)
        with self._origin("127.0.0.1", 11434) as origin:
            server = view.ThreadingHTTPServer(("127.0.0.1", 0), view.make_handler(install))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.addCleanup(server.shutdown)
            self.addCleanup(server.server_close)
            self.addCleanup(lambda: thread.join(timeout=2))
            port = server.server_address[1]
            # http.client does not consult http_proxy. The app's own client does.
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
            payload = json.dumps(
                {
                    "text": ask,
                    "model": "gemma2:2b",
                    "session_id": session_id,
                    "temperature": 0.7,
                    "top_p": 0.9,
                }
            ).encode("utf-8")
            conn.request("POST", "/api/chat", body=payload, headers={"Content-Type": "application/json"})
            response = conn.getresponse()
            raw = response.read()
            conn.close()
        self.assertEqual(response.status, 200, raw)
        rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
        self._assert_direct(
            proxy,
            origin,
            rows,
            markers,
            caption="Reply stayed on this machine.",
            selected="gemma2:2b",
        )


if __name__ == "__main__":
    unittest.main()
