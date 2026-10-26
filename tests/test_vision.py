"""Vision wiring: a local vision model answers image turns, image bytes
only ever travel to this machine's Ollama, refusals are plain sentences,
and the transcript keeps a placeholder instead of the picture."""

from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from mrs_public.chat import stream_chat
from mrs_public.view import ensure_install, state, update_profile

PNG_1PX = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAwMCAO+ip1sAAAAASUVORK5CYII="
GIF_BYTES = b"GIF89a" + b"\x00" * 32
TAGS = ["gemma2:2b", "moondream:latest"]


class _StreamBody:
    def __init__(self, raw: bytes):
        self._raw = io.BytesIO(raw)

    def readline(self) -> bytes:
        return self._raw.readline()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _TagsBody:
    def __init__(self, names):
        self._payload = json.dumps({"models": [{"name": name} for name in names]}).encode()

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def scan_with(names):
    def opener(url, timeout=3):
        return _TagsBody(names)

    return opener


def chat_replying(captured: dict, text: str = "I see it."):
    def opener(req, timeout=180):
        captured["payload"] = json.loads(req.data.decode())
        body = json.dumps({"message": {"content": text}, "done": True}).encode() + b"\n"
        return _StreamBody(body)

    return opener


def run_turn(install: Path, **kwargs):
    events = list(stream_chat(install, **kwargs))
    done = [event for event in events if event.get("done")]
    return events, done[-1] if done else None


class VisionRoleWiringTest(unittest.TestCase):
    def test_text_mention_picks_the_vision_role_when_a_local_vision_model_exists(self):
        install = Path(tempfile.mkdtemp())
        captured: dict = {}
        _, done = run_turn(
            install,
            text="describe this photo for me",
            model="gemma2:2b",
            opener=chat_replying(captured),
            scan_opener=scan_with(TAGS),
        )
        self.assertEqual(done["role"], "vision")
        # No attachment, no model swap: the role is a prompt, not a reroute.
        self.assertEqual(captured["payload"]["model"], "gemma2:2b")
        self.assertFalse(done["vision"])
        for message in captured["payload"]["messages"]:
            self.assertNotIn("images", message)

    def test_text_mention_without_a_vision_model_stays_companion(self):
        install = Path(tempfile.mkdtemp())
        captured: dict = {}
        _, done = run_turn(
            install,
            text="describe this photo for me",
            model="gemma2:2b",
            opener=chat_replying(captured),
            scan_opener=scan_with(["gemma2:2b"]),
        )
        self.assertEqual(done["role"], "companion")


class VisionPayloadTest(unittest.TestCase):
    def test_an_attached_image_rides_the_payload_to_the_vision_model(self):
        install = Path(tempfile.mkdtemp())
        captured: dict = {}
        _, done = run_turn(
            install,
            text="what is in this image?",
            model="gemma2:2b",
            image={"type": "image/png", "data": PNG_1PX},
            opener=chat_replying(captured),
            scan_opener=scan_with(TAGS),
        )
        payload = captured["payload"]
        self.assertEqual(payload["model"], "moondream:latest")
        self.assertEqual(payload["options"]["num_ctx"], 4096)  # the vision sampler
        users = [m for m in payload["messages"] if m["role"] == "user"]
        self.assertEqual(users[-1]["images"], [PNG_1PX])
        self.assertEqual(users[-1]["content"], "what is in this image?")
        self.assertEqual(done["role"], "vision")
        self.assertEqual(done["model"], "moondream:latest")
        self.assertTrue(done["vision"])


class CloudPickerTest(unittest.TestCase):
    def test_a_cloud_selection_still_routes_the_image_to_local_vision(self):
        install = Path(tempfile.mkdtemp())
        captured: dict = {}
        _, done = run_turn(
            install,
            text="look at this",
            model="nemotron-3-super:cloud",
            image={"type": "image/png", "data": PNG_1PX},
            opener=chat_replying(captured),
            scan_opener=scan_with(["nemotron-3-super:cloud", "moondream:latest"]),
        )
        self.assertEqual(captured["payload"]["model"], "moondream:latest")
        self.assertFalse(captured["payload"]["model"].endswith(":cloud"))
        self.assertTrue(done["vision"])
        self.assertEqual(done["model"], "moondream:latest")
        self.assertEqual(done["session"]["model"], "moondream:latest")


class ImageRefusalTest(unittest.TestCase):
    def _refused(self, image, tags=TAGS) -> str:
        install = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError) as ctx:
            list(
                stream_chat(
                    install,
                    text="look",
                    model="gemma2:2b",
                    image=image,
                    opener=chat_replying({}),
                    scan_opener=scan_with(tags),
                )
            )
        return str(ctx.exception)

    def test_an_oversize_image_is_refused(self):
        raw = base64.b64decode(PNG_1PX) + b"\x00" * 10_000_001
        message = self._refused({"type": "image/png", "data": base64.b64encode(raw).decode()})
        self.assertIn("too large", message)

    def test_a_file_that_is_not_the_image_it_claims_is_refused(self):
        message = self._refused({"type": "image/png", "data": base64.b64encode(GIF_BYTES).decode()})
        self.assertIn("not the image it claims to be", message)

    def test_an_unlisted_type_is_refused(self):
        message = self._refused({"type": "image/bmp", "data": PNG_1PX})
        self.assertIn("not one she can look at", message)

    def test_malformed_base64_is_refused(self):
        message = self._refused({"type": "image/png", "data": "!!! not base64 !!!"})
        self.assertIn("did not arrive whole", message)

    def test_an_image_with_no_vision_model_is_refused_and_nothing_is_sent(self):
        install = Path(tempfile.mkdtemp())
        calls: list = []

        def opener(req, timeout=180):
            calls.append(req)
            return _StreamBody(b'{"message":{"content":"x"},"done":true}\n')

        with self.assertRaises(ValueError) as ctx:
            list(
                stream_chat(
                    install,
                    text="look",
                    model="gemma2:2b",
                    image={"type": "image/png", "data": PNG_1PX},
                    opener=opener,
                    scan_opener=scan_with(["gemma2:2b"]),
                )
            )
        self.assertIn("not sent anywhere", str(ctx.exception))
        self.assertEqual(calls, [])


class SessionPersistenceTest(unittest.TestCase):
    def test_the_session_keeps_a_placeholder_never_the_bytes(self):
        install = Path(tempfile.mkdtemp())
        _, done = run_turn(
            install,
            text="what is this?",
            model="gemma2:2b",
            image={"type": "image/png", "data": PNG_1PX},
            opener=chat_replying({}),
            scan_opener=scan_with(TAGS),
        )
        path = install / "state" / "sessions" / f"{done['session']['id']}.json"
        raw = path.read_text(encoding="utf-8")
        self.assertNotIn(PNG_1PX, raw)
        users = [m["content"] for m in done["session"]["messages"] if m["role"] == "user"]
        self.assertEqual(users, ["what is this? [image]"])
        rows = [m for m in done["session"]["messages"] if m["role"] == "user"]
        self.assertTrue(rows[0].get("image"))

    def test_an_image_only_turn_stores_the_bare_placeholder(self):
        install = Path(tempfile.mkdtemp())
        _, done = run_turn(
            install,
            text="",
            model="gemma2:2b",
            image={"type": "image/png", "data": PNG_1PX},
            opener=chat_replying({}),
            scan_opener=scan_with(TAGS),
        )
        users = [m["content"] for m in done["session"]["messages"] if m["role"] == "user"]
        self.assertEqual(users, ["[image]"])


class FollowUpHistoryTest(unittest.TestCase):
    def test_history_on_the_wire_drops_the_placeholder(self):
        install = Path(tempfile.mkdtemp())
        _, done = run_turn(
            install,
            text="what is this?",
            model="gemma2:2b",
            image={"type": "image/png", "data": PNG_1PX},
            opener=chat_replying({}),
            scan_opener=scan_with(TAGS),
        )
        captured: dict = {}
        run_turn(
            install,
            text="and now?",
            model="gemma2:2b",
            session_id=done["session"]["id"],
            opener=chat_replying(captured),
            scan_opener=scan_with(TAGS),
        )
        users = [m for m in captured["payload"]["messages"] if m["role"] == "user"]
        self.assertEqual([m["content"] for m in users], ["what is this?", "and now?"])
        for message in users:
            self.assertNotIn("images", message)


class PageVisionTest(unittest.TestCase):
    def test_state_reports_the_vision_model(self):
        install = ensure_install(Path(tempfile.mkdtemp()))
        update_profile(install, {"scan_allowed": True})
        snapshot = state(install, scan_with(TAGS))
        self.assertEqual(snapshot["vision_model"], "moondream:latest")
        snapshot = state(install, scan_with(["gemma2:2b"]))
        self.assertEqual(snapshot["vision_model"], "")

    def test_the_page_carries_the_attach_control_and_the_provenance_line(self):
        page = Path(__file__).resolve().parents[1] / "mrs_public" / "studio_page.html"
        text = page.read_text(encoding="utf-8")
        self.assertIn('id="attach-image"', text)
        self.assertIn('id="vision-note"', text)
        self.assertIn("The local vision model (", text)
        self.assertIn("did the looking", text)


if __name__ == "__main__":
    unittest.main()
