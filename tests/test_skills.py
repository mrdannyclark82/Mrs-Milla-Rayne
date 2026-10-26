"""Skills: instruction packs from the install's own folder. They teach,
they never grant. The memory viewer shows what she has learned."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

from mrs_public.boot import first_boot
from mrs_public.chat import stream_chat
from mrs_public.memory import Memory
from mrs_public.skills import load_skills, pick_skill
from mrs_public.view import ensure_install, serve, state

MEAL = """name: Meal Planner
when: meal plan, recipe, grocery list

Plan the week simply. Ask about budget before ingredients.
"""


class Body:
    def __init__(self, raw: bytes):
        self._raw = io.BytesIO(raw)

    def read(self):
        return self._raw.getvalue()

    def readline(self):
        return self._raw.readline()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def install_with_skill() -> Path:
    install = ensure_install(Path(tempfile.mkdtemp()))
    (install / "skills" / "meal-planner.md").write_text(MEAL, encoding="utf-8")
    return install


class LoadSkillsTest(unittest.TestCase):
    def test_parses_name_triggers_body(self):
        install = install_with_skill()
        skills = load_skills(install)
        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "Meal Planner")
        self.assertIn("recipe", skills[0].triggers)
        self.assertIn("Plan the week simply.", skills[0].body)

    def test_skips_readme_and_empty(self):
        install = install_with_skill()
        (install / "skills" / "README.md").write_text(MEAL, encoding="utf-8")
        (install / "skills" / "empty.md").write_text("name: Nobody\n", encoding="utf-8")
        names = [s.name for s in load_skills(install)]
        self.assertEqual(names, ["Meal Planner"])

    def test_pick_matches_triggers_only(self):
        install = install_with_skill()
        skills = load_skills(install)
        self.assertEqual(pick_skill(skills, "a recipe for soup").name, "Meal Planner")
        self.assertIsNone(pick_skill(skills, "how is the weather"))


class SkillChatTest(unittest.TestCase):
    def test_skill_rides_the_turn_and_is_named(self):
        install = install_with_skill()
        captured = {}

        def fetch(req, timeout=180):
            captured["payload"] = json.loads(req.data.decode())
            return Body(b'{"message": {"content": "Soup it is."}, "done": true}\n')

        rows = list(
            stream_chat(install, text="I need a recipe", model="gemma2:2b", opener=fetch)
        )
        done = rows[-1]
        self.assertEqual(done["skill"], "Meal Planner")
        system = captured["payload"]["messages"][0]["content"]
        self.assertIn("Skill in use: Meal Planner", system)
        self.assertIn("Plan the week simply.", system)

    def test_no_skill_no_field(self):
        install = install_with_skill()

        def fetch(req, timeout=180):
            return Body(b'{"message": {"content": "Fine day."}, "done": true}\n')

        rows = list(
            stream_chat(install, text="how is the weather", model="gemma2:2b", opener=fetch)
        )
        self.assertEqual(rows[-1]["skill"], "")


class MemoryViewTest(unittest.TestCase):
    def setUp(self):
        self.install = ensure_install(Path(tempfile.mkdtemp()))
        memory = Memory(self.install)
        memory.add("canon", text="The user is called Sam.")
        memory.add("episodes", text="talked about soup", outcome="said")
        self.server = serve(self.install, 0)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_memory_endpoint_shows_the_piles(self):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/api/memory")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertEqual(data["canon"][0]["text"], "The user is called Sam.")
        self.assertEqual(data["episodes"][0]["text"], "talked about soup")

    def test_state_lists_skills(self):
        (self.install / "skills" / "meal-planner.md").write_text(MEAL, encoding="utf-8")
        snapshot = state(self.install)
        self.assertEqual(snapshot["skills"], ["Meal Planner"])


class SetupNotesTest(unittest.TestCase):
    def test_first_boot_carries_setup_notes(self):
        def fetch(url, timeout=3):
            return Body(json.dumps({"models": [{"name": "gemma2:2b"}]}).encode())

        dest = Path(tempfile.mkdtemp()) / "install"
        result = first_boot(dest, permission=True, opener=fetch)
        self.assertTrue(result.ok, result.reason)
        self.assertEqual(len(result.setup_notes), 4)
        joined = " ".join(result.setup_notes)
        self.assertIn("voice_reference.wav", joined)
        self.assertIn("private_bases.txt", joined)
        self.assertIn("skills/", joined)


if __name__ == "__main__":
    unittest.main()
