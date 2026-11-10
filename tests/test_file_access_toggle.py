"""A session directory granted while local file access is on must not be
listed or read into a model request after that access is turned off.

The direct home-file route already refuses in that state. These tests
follow the same profile toggle, then the chat path: a directory set with
"work in" or with the panel's session-work request, a later turn, and the
bytes that turn would send to the model endpoint.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from mrs_public.chat import stream_chat
from mrs_public.providers import Provider
from mrs_public.view import ensure_install, load_profile, serve, update_profile

SIBLING = "mmr-secret-ledger-9f3a.txt"
NESTED = "notes/mmr-secret-vault-9f3a.txt"
HEAD = "MMR-CANARY-HEAD-9f3a"
TAIL = "MMR-CANARY-TAIL-9f3a"
FILE_MARK = "BEGIN FILE TEXT"
CLOUD_URL = "http://203.0.113.10/v1"
OLLAMA_MODEL = "remote-chat:cloud"
REMOTE_MODEL = "remote-chat"


class _Body:
    def __init__(self, raw: bytes):
        self._raw = io.BytesIO(raw)

    def readline(self):
        return self._raw.readline()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Capture:
    """Stand-in for urlopen. The chat code builds the request itself."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, req, timeout=180):
        self.calls.append(
            {
                "url": req.full_url,
                "body": json.loads(req.data.decode()),
            }
        )
        if req.full_url.rstrip("/").endswith("/chat/completions"):
            raw = (
                b'data: {"choices":[{"delta":{"content":"ok"}}]}\n'
                b"\n"
                b"data: [DONE]\n"
            )
        else:
            raw = b'{"message":{"content":"ok"},"done":true}\n'
        return _Body(raw)


def _wire(payload: dict) -> str:
    return "\n".join(str(item.get("content") or "") for item in payload["messages"])


def _found(payload: dict, tokens: tuple[str, ...]) -> list[str]:
    text = _wire(payload)
    return [token for token in tokens if token in text]


def _private_tree(root: Path) -> Path:
    work = root / "private-session"
    (work / "notes").mkdir(parents=True)
    (work / SIBLING).write_text("sibling name only\n", encoding="utf-8")
    # Longer than the chat file cap, so a truncated read still carries HEAD.
    body = HEAD + "\n" + ("q" * 13000) + "\n" + TAIL + "\n"
    (work / "notes" / "mmr-secret-vault-9f3a.txt").write_text(body, encoding="utf-8")
    return work


def _owned_dirs():
    install = ensure_install(Path(tempfile.mkdtemp(prefix="mrs-install-")))
    # The toggle stores Path.home() as the granted root. Keep the private
    # tree under that root so the grant path is the one the profile writes.
    private_root = Path(tempfile.mkdtemp(prefix=".mrs-toggle-", dir=Path.home()))
    work = _private_tree(private_root)
    return install, private_root, work


def _cleanup(install: Path, private_root: Path) -> None:
    shutil.rmtree(install, ignore_errors=True)
    shutil.rmtree(private_root, ignore_errors=True)


def _turn(install: Path, capture: _Capture, *, text: str, model: str, session_id: str = "", provider=None):
    profile = load_profile(install)
    return list(
        stream_chat(
            install,
            text=text,
            model=model,
            session_id=session_id,
            file_access=bool(profile.get("file_access")),
            opener=capture,
            provider=provider,
        )
    )


def _request(port: int, method: str, path: str, payload: dict | None = None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _events(raw: bytes) -> list[dict]:
    rows = []
    for line in raw.decode().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


class FileAccessToggleTest(unittest.TestCase):
    def setUp(self):
        self.install, self.private_root, self.work = _owned_dirs()
        self.capture = _Capture()

    def tearDown(self):
        _cleanup(self.install, self.private_root)

    def _grant_by_chat(self) -> str:
        update_profile(self.install, {"file_access": True})
        rows = _turn(
            self.install,
            self.capture,
            text=f"work in {self.work}",
            model=OLLAMA_MODEL,
        )
        self.capture.calls.clear()
        session = rows[-1]["session"]
        self.assertEqual(Path(session["work_path"]), self.work.resolve())
        return session["id"]

    def test_private_names_are_not_sent_after_file_access_is_turned_off(self):
        session_id = self._grant_by_chat()
        _turn(
            self.install,
            self.capture,
            text="hello there",
            model=OLLAMA_MODEL,
            session_id=session_id,
        )
        granted = self.capture.calls[-1]
        self.assertTrue(granted["url"].endswith("/api/chat"))
        self.assertEqual(granted["body"]["model"], OLLAMA_MODEL)
        self.assertIn(SIBLING, _wire(granted["body"]))
        self.assertIn(NESTED, _wire(granted["body"]))

        update_profile(self.install, {"file_access": False})
        self.assertFalse(load_profile(self.install)["file_access"])
        _turn(
            self.install,
            self.capture,
            text="hello there",
            model=OLLAMA_MODEL,
            session_id=session_id,
        )
        closed = self.capture.calls[-1]
        leaked = _found(closed["body"], (SIBLING, NESTED, HEAD))
        self.assertEqual(
            leaked,
            [],
            "model request still contains private names from the session directory",
        )

    def test_private_file_text_is_not_sent_after_file_access_is_turned_off(self):
        session_id = self._grant_by_chat()
        rows = _turn(
            self.install,
            self.capture,
            text=f"please read {NESTED}",
            model=OLLAMA_MODEL,
            session_id=session_id,
        )
        granted = self.capture.calls[-1]
        self.assertEqual([row["file"] for row in rows if "file" in row], [{"path": NESTED, "ok": True}])
        granted_text = _wire(granted["body"])
        self.assertIn(HEAD, granted_text)
        self.assertIn(FILE_MARK, granted_text)
        self.assertIn(SIBLING, granted_text)
        self.assertNotIn(TAIL, granted_text)

        update_profile(self.install, {"file_access": False})
        self.assertFalse(load_profile(self.install)["file_access"])
        _turn(
            self.install,
            self.capture,
            text=f"please read {NESTED}",
            model=OLLAMA_MODEL,
            session_id=session_id,
        )
        closed = self.capture.calls[-1]
        # NESTED is in the user's own message. SIBLING is not, and neither
        # canary is: those arrive only if this turn walks or reads the tree.
        leaked = _found(closed["body"], (SIBLING, HEAD, TAIL, FILE_MARK))
        self.assertEqual(
            leaked,
            [],
            "model request still contains the private file or its siblings",
        )

    def test_a_new_directory_after_file_access_is_off_is_not_read(self):
        update_profile(self.install, {"file_access": True})
        update_profile(self.install, {"file_access": False})
        self.assertFalse(load_profile(self.install)["file_access"])
        try:
            _turn(
                self.install,
                self.capture,
                text=f"work in {self.work} and please read {NESTED}",
                model=OLLAMA_MODEL,
            )
        except ValueError:
            pass
        blob = "\n".join(_wire(call["body"]) for call in self.capture.calls)
        self.assertNotIn(HEAD, blob)
        self.assertNotIn(SIBLING, blob)
        self.assertNotIn(FILE_MARK, blob)

    def test_cloud_endpoint_does_not_receive_the_private_tree_after_the_panel_grant_is_turned_off(self):
        server = serve(self.install, 0, chat_opener=self.capture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        port = server.server_address[1]

        status, raw = _request(
            port,
            "POST",
            "/api/profile",
            {
                "file_access": True,
                "providers": [
                    {
                        "id": "remote",
                        "kind": "openai",
                        "url": CLOUD_URL,
                        "label": "Remote",
                    }
                ],
            },
        )
        self.assertEqual(status, 200)
        profile = json.loads(raw.decode())
        self.assertTrue(profile["file_access"])
        self.assertEqual(Path(profile["user_root"]), Path.home())

        status, raw = _request(port, "POST", "/api/sessions", {"model": REMOTE_MODEL})
        self.assertEqual(status, 200)
        session_id = json.loads(raw.decode())["id"]

        status, raw = _request(
            port,
            "POST",
            "/api/session-work",
            {"session_id": session_id, "path": str(self.work)},
        )
        self.assertEqual(status, 200)
        self.assertEqual(Path(json.loads(raw.decode())["work_path"]), self.work.resolve())

        status, raw = _request(
            port,
            "POST",
            "/api/chat",
            {
                "text": f"please read {NESTED}",
                "model": REMOTE_MODEL,
                "session_id": session_id,
                "provider": "remote",
            },
        )
        self.assertEqual(status, 200)
        done = [row for row in _events(raw) if row.get("done")]
        self.assertEqual(done[-1]["local"], False)
        self.assertEqual(done[-1]["provider"], "Remote")
        granted = self.capture.calls[-1]
        self.assertEqual(granted["url"], CLOUD_URL + "/chat/completions")
        granted_text = _wire(granted["body"])
        self.assertIn(HEAD, granted_text)
        self.assertIn(SIBLING, granted_text)
        self.assertNotIn(TAIL, granted_text)

        status, raw = _request(port, "POST", "/api/profile", {"file_access": False})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(raw.decode())["file_access"])
        status, raw = _request(port, "GET", "/api/state")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(raw.decode())["file_access"])

        rel = self.work.joinpath("notes", "mmr-secret-vault-9f3a.txt").resolve().relative_to(Path.home()).as_posix()
        status, raw = _request(port, "GET", "/api/home-file?rel=" + urllib.parse.quote(rel))
        self.assertEqual(status, 400)
        self.assertNotIn(HEAD, raw.decode())
        self.assertIn(b"local file access is off", raw)

        status, raw = _request(
            port,
            "POST",
            "/api/session-work",
            {"session_id": session_id, "path": str(self.work)},
        )
        self.assertEqual(status, 400)

        with self.subTest("listing"):
            status, raw = _request(
                port,
                "POST",
                "/api/chat",
                {
                    "text": "hello there",
                    "model": REMOTE_MODEL,
                    "session_id": session_id,
                    "provider": "remote",
                },
            )
            self.assertEqual(status, 200)
            closed = self.capture.calls[-1]
            self.assertEqual(closed["url"], CLOUD_URL + "/chat/completions")
            # The earlier granted turn stored "please read <nested>" in the
            # transcript, so the nested name is the user's own words.
            # The sibling name is not, and neither is the file body.
            leaked = _found(closed["body"], (SIBLING, HEAD))
            self.assertEqual(leaked, [])

        with self.subTest("file text"):
            status, raw = _request(
                port,
                "POST",
                "/api/chat",
                {
                    "text": f"please read {NESTED}",
                    "model": REMOTE_MODEL,
                    "session_id": session_id,
                    "provider": "remote",
                },
            )
            self.assertEqual(status, 200)
            closed = self.capture.calls[-1]
            self.assertEqual(closed["url"], CLOUD_URL + "/chat/completions")
            leaked = _found(closed["body"], (SIBLING, HEAD, TAIL, FILE_MARK))
            self.assertEqual(leaked, [])

    def test_openai_transport_helper_matches_the_cloud_request_shape(self):
        """Same outbound builder, called with the provider object the handler passes."""
        update_profile(
            self.install,
            {
                "file_access": True,
                "providers": [
                    {"id": "remote", "kind": "openai", "url": CLOUD_URL, "label": "Remote"}
                ],
            },
        )
        provider = Provider("remote", "openai", CLOUD_URL, "Remote")
        rows = _turn(
            self.install,
            self.capture,
            text=f"work in {self.work}",
            model=REMOTE_MODEL,
            provider=provider,
        )
        session_id = rows[-1]["session"]["id"]
        self.capture.calls.clear()
        update_profile(self.install, {"file_access": False})
        _turn(
            self.install,
            self.capture,
            text="hello there",
            model=REMOTE_MODEL,
            session_id=session_id,
            provider=provider,
        )
        closed = self.capture.calls[-1]
        self.assertEqual(closed["url"], CLOUD_URL + "/chat/completions")
        leaked = _found(closed["body"], (SIBLING, NESTED, HEAD))
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
