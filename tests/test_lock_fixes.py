"""Pre-lock fixes: cloud honesty, sampler wiring, corruption tolerance,
the deliberate grant path, the on-open review wiring, write-on-change."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mrs_public import __version__
from mrs_public.chat import list_sessions, load_session, save_session, stream_chat
from mrs_public.memory import Memory
from mrs_public.models import is_cloud, public_tags, suggest
from mrs_public.recall import ensure_roots, learn
from mrs_public.view import ensure_install, serve, state, update_profile


class _StreamBody:
    def __init__(self, raw: bytes):
        self._raw = io.BytesIO(raw)

    def readline(self) -> bytes:
        return self._raw.readline()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class CloudHonestyTest(unittest.TestCase):
    def test_is_cloud_reads_the_suffix(self):
        self.assertTrue(is_cloud("nemotron-3-super:cloud"))
        self.assertTrue(is_cloud("Some-Model:CLOUD"))
        self.assertFalse(is_cloud("gemma2:2b"))
        self.assertFalse(is_cloud("cloudy:7b"))
        self.assertFalse(is_cloud(""))

    def test_cloud_tags_stay_listed_but_are_never_auto_picked(self):
        tags = ["big-reasoner:cloud", "gemma2:2b"]
        self.assertIn("big-reasoner:cloud", public_tags(tags))
        picked = suggest(tags)
        self.assertEqual(picked["companion"], "gemma2:2b")
        only_cloud = suggest(["big-reasoner:cloud"])
        self.assertIsNone(only_cloud["companion"])


class SamplerPayloadTest(unittest.TestCase):
    def test_num_ctx_and_role_defaults_reach_the_payload(self):
        install = Path(tempfile.mkdtemp())
        captured = {}

        def opener(req, timeout=180):
            captured["payload"] = json.loads(req.data.decode())
            return _StreamBody(b'{"message":{"content":"Hi."},"done":true}\n')

        list(stream_chat(install, text="hi", model="gemma2:2b", temperature=0.33, opener=opener))
        options = captured["payload"]["options"]
        self.assertEqual(options["num_ctx"], 8192)  # companion default from persona/sampler.json
        self.assertEqual(options["temperature"], 0.33)  # the user's slider wins
        self.assertEqual(options["top_p"], 0.9)


class CorruptionToleranceTest(unittest.TestCase):
    def test_memory_read_skips_torn_lines(self):
        install = Path(tempfile.mkdtemp())
        memory = Memory(install)
        memory.add("canon", kind="who", text="A fact.")
        pile = install / "state" / "canon.jsonl"
        with pile.open("a", encoding="utf-8") as handle:
            handle.write('{"id": "torn", "tex\n')
            handle.write("5\n")
        rows = memory.read("canon")
        self.assertEqual([row["text"] for row in rows], ["A fact."])

    def test_list_sessions_skips_unreadable_files(self):
        install = Path(tempfile.mkdtemp())
        good = save_session(install, {"id": "abc123", "title": "Kept", "messages": [], "model": "gemma2:2b"})
        bad = install / "state" / "sessions" / "zzz999.json"
        bad.write_text('{"id": "zzz999", "mess', encoding="utf-8")
        rows = list_sessions(install)
        self.assertEqual([row["id"] for row in rows], [good["id"]])

    def test_save_session_is_atomic_and_round_trips(self):
        install = Path(tempfile.mkdtemp())
        data = {"id": "abc123", "title": "T", "messages": [{"role": "user", "content": "hi"}], "model": "gemma2:2b"}
        save_session(install, data)
        folder = install / "state" / "sessions"
        self.assertEqual([p.name for p in folder.iterdir()], ["abc123.json"])
        self.assertEqual(load_session(install, "abc123")["title"], "T")


class GrantPathTest(unittest.TestCase):
    def test_a_sentence_never_grants_but_a_name_is_learned(self):
        install = Path(tempfile.mkdtemp())
        learn(install, "I would never grant file access to an app like this.")
        learn(install, "My name is Ada Byron.")
        memory = Memory(install)
        texts = [row["text"] for row in memory.read("canon")]
        self.assertEqual(texts, ["The user's name is Ada Byron."])
        profile_path = install / "state" / "profile.json"
        if profile_path.exists():
            self.assertFalse(json.loads(profile_path.read_text(encoding="utf-8")).get("file_access"))

    def test_ensure_roots_never_defaults_user_root_to_home(self):
        install = Path(tempfile.mkdtemp())
        path = install / "state" / "profile.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"file_access": True}), encoding="utf-8")
        profile = ensure_roots(install)
        self.assertFalse(profile.get("user_root"))

    def test_the_toggle_remains_the_deliberate_grant(self):
        install = Path(tempfile.mkdtemp())
        Memory(install)  # a served install always has its state dir
        profile = update_profile(install, {"file_access": True})
        self.assertTrue(profile["file_access"])
        self.assertTrue(profile["user_root"])


class StartupWiringTest(unittest.TestCase):
    def test_serve_runs_the_daily_review_once(self):
        install = Path(tempfile.mkdtemp())
        memory = Memory(install)
        memory.add("episodes", text="The patch landed.", outcome="done", files=["src/app.py"])
        server = serve(install, 0)
        server.server_close()
        self.assertEqual(len(Memory(install).read("reviews")), 1)
        server = serve(install, 0)
        server.server_close()
        self.assertEqual(len(Memory(install).read("reviews")), 1)

    def test_state_reports_the_version(self):
        install = ensure_install(Path(tempfile.mkdtemp()))
        self.assertEqual(__version__, "1.1.0")
        self.assertEqual(state(install)["version"], "1.1.0")

    def test_profile_is_written_only_on_change(self):
        install = Path(tempfile.mkdtemp())
        Memory(install)  # a served install always has its state dir
        with mock.patch("mrs_public.recall._write_profile") as writer:
            writer.side_effect = lambda inst, prof: Path(inst, "state", "profile.json").write_text(
                json.dumps(prof, indent=2) + "\n", encoding="utf-8"
            )
            ensure_roots(install)
            ensure_roots(install)
            ensure_roots(install)
        self.assertEqual(writer.call_count, 1)


if __name__ == "__main__":
    unittest.main()
