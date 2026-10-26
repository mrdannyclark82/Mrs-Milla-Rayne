"""The canvas page we keep. Loopback, desk files, no private language."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from mrs_public.guard import leaks
from mrs_public.view import PAGE, serve


class CanvasViewTest(unittest.TestCase):
    def setUp(self):
        self.install = Path(tempfile.mkdtemp())
        bases = self.install / "private_bases.txt"
        bases.write_text("house-rayne\n", encoding="utf-8")
        os.environ["MRS_PUBLIC_PRIVATE_BASES"] = str(bases)
        self.server = serve(self.install, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _request(self, method, path, body=None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=3)
        headers = {}
        raw = None
        if body is not None:
            raw = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(raw))
        conn.request(method, path, body=raw, headers=headers)
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res.status, data

    def test_page_has_no_private_words(self):
        page = PAGE.read_text(encoding="utf-8")
        self.assertEqual(leaks(page), [])
        self.assertIn("aside class=\"nav\"", page)
        self.assertNotIn("agent_respond", page)
        self.assertNotIn("house-rayne", page)
        status, body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertNotIn("Public prompt", page)
        self.assertNotIn("skill-pill", page)
        self.assertNotIn("use_prompt", page)
        self.assertIn("Enter sends", page)
        self.assertIn('event.key !== "Enter"', page)
        self.assertIn(b"Mrs. Milla Rayne", body)
        self.assertIn(b"Execution", body)

    def test_add_shows_up_and_escape_is_refused(self):
        status, body = self._request(
            "POST",
            "/api/place",
            {"name": "notes/today.txt", "content": "hello from the desk"},
        )
        self.assertEqual(status, 200, body)
        self.assertTrue((self.install / "workspace" / "notes" / "today.txt").is_file())
        status, body = self._request("GET", "/api/state")
        state = json.loads(body)
        self.assertFalse(state["execute"])
        self.assertEqual(state["additions"][0]["relative"], "notes/today.txt")
        status, body = self._request("GET", "/api/file?rel=" + "notes/today.txt")
        self.assertIn("hello from the desk", json.loads(body)["content"])
        status, body = self._request("GET", "/api/file?rel=../secret.txt")
        self.assertEqual(status, 400)

    def test_download_is_the_desk_zip(self):
        self._request("POST", "/api/place", {"name": "piece.txt", "content": "done"})
        status, body = self._request("GET", "/api/download.zip")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"PK"))
        self.assertIn(b"piece.txt", body)

    def test_chat_wears_the_public_prompt_and_refuses_house_weights(self):
        import io

        class Body:
            def __init__(self, raw):
                self._raw = io.BytesIO(raw)

            def readline(self):
                return self._raw.readline()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        seen = {}

        def opener(req, timeout=180):
            payload = json.loads(req.data.decode())
            seen["system"] = payload["messages"][0]["content"]
            raw = b'{"message":{"content":"Hello from the desk."},"done":true}\n'
            return Body(raw)

        server = serve(self.install, 0, chat_opener=opener)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=3)
            raw = json.dumps({"model": "gemma2:2b", "text": "hi", "use_prompt": True}).encode()
            conn.request("POST", "/api/chat", body=raw, headers={"Content-Type": "application/json", "Content-Length": str(len(raw))})
            res = conn.getresponse()
            data = res.read()
            conn.close()
            self.assertEqual(res.status, 200, data)
            self.assertIn(b"Hello from the desk.", data)
            self.assertIn("Mrs. Milla Rayne", seen["system"])
            self.assertEqual(leaks(seen["system"]), [])
            conn = HTTPConnection("127.0.0.1", port, timeout=3)
            raw = json.dumps({"model": "house-rayne:latest", "text": "hi"}).encode()
            conn.request("POST", "/api/chat", body=raw, headers={"Content-Type": "application/json", "Content-Length": str(len(raw))})
            res = conn.getresponse()
            data = res.read()
            conn.close()
            self.assertEqual(res.status, 400, data)
            self.assertIn(b"stays on the house", data)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
