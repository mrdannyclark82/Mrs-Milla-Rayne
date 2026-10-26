"""Personalized memory, the desk, and the on-open review."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from mrs_public.bounds import accept_directory, app_root, can_delete, zone
from mrs_public.canvas import delete_hers, download_desk, place, read_home
from mrs_public.memory import Memory
from mrs_public.pack import read_prompt
from mrs_public.recall import context_block, learn_history, turn_note
from mrs_public.review import on_open


class MemoryCanvasTest(unittest.TestCase):
    def test_piles_are_visible_and_deletable(self):
        install = Path(tempfile.mkdtemp())
        memory = Memory(install)
        kept = memory.add("canon", who="Ada", decision="Use the local model.")
        memory.add("episodes", text="She wrote the note.", outcome="done", files=["note.txt"])
        self.assertEqual(len(memory.read("canon")), 1)
        memory.delete("canon", kept["id"])
        self.assertEqual(memory.read("canon"), [])

    def test_her_workspace_does_not_require_file_access(self):
        install = Path(tempfile.mkdtemp())
        row = place(install, "src/app.py", "print(1)\n", file_access=False)
        self.assertTrue((install / "workspace" / "src" / "app.py").is_file())
        self.assertEqual(row["where"], "hers")
        self.assertFalse(row["executed"])
        self.assertEqual(row["relative"], "src/app.py")

    def test_closed_desk_downloads_without_touching_a_home(self):
        install = Path(tempfile.mkdtemp())
        place(install, "note.txt", "hello\n", file_access=False)
        archive = download_desk(install)
        self.assertTrue(archive.name.startswith("canvas-"))
        self.assertEqual(archive.parent, install / "state" / "downloads")
        self.assertIn("note.txt", archive.read_bytes().decode("latin1"))

    def test_path_escape_is_refused(self):
        install = Path(tempfile.mkdtemp())
        with self.assertRaises(ValueError):
            place(install, "../outside.txt", "nope", file_access=False)

    def test_rwx_stops_at_her_workspace(self):
        install = Path(tempfile.mkdtemp())
        place(install, "note.txt", "keep")
        self.assertTrue(delete_hers(install, "note.txt")["deleted"])
        self.assertFalse((install / "workspace" / "note.txt").exists())
        secret = install / "state" / "profile.json"
        secret.parent.mkdir(parents=True, exist_ok=True)
        secret.write_text("{}", encoding="utf-8")
        self.assertFalse(can_delete(secret, install))
        with self.assertRaises(ValueError):
            delete_hers(install, "../state/profile.json")
        home = Path(tempfile.mkdtemp())
        (home / "Projects").mkdir()
        (home / "Projects" / "note.txt").write_text("hello", encoding="utf-8")
        self.assertEqual(zone(home / "Projects" / "note.txt", install, file_access=True, user_root=str(home)), "home")
        self.assertEqual(read_home(install, "Projects/note.txt", user_root=str(home))["content"], "hello")
        self.assertEqual(zone(Path("/etc/passwd"), install, file_access=True, user_root=str(home)), "closed")
        self.assertEqual(zone(app_root() / "mrs_public" / "bounds.py", install, file_access=True, user_root=str(Path.home())), "closed")
        with self.assertRaises(ValueError):
            read_home(install, "Projects/note.txt", user_root="/etc")
        self.assertEqual(
            accept_directory(str(home / "Projects"), install, file_access=True, user_root=str(home)),
            (home / "Projects").resolve(),
        )
        with self.assertRaises(ValueError):
            accept_directory("/etc", install, file_access=True, user_root=str(home))
        with self.assertRaises(ValueError):
            accept_directory(str(app_root()), install, file_access=True, user_root=str(Path.home()))

    def test_introduction_becomes_canon_and_phrases_do_not_grant(self):
        install = Path(tempfile.mkdtemp())
        memory = Memory(install)
        memory.add("episodes", text="Hello Mrs. Rayne", outcome="said")
        memory.add("episodes", text="Very nice to meet you. My name is Jordan Ellis.", outcome="said")
        memory.add("episodes", text="ok you have been granted local file access to my system.", outcome="said")
        learn_history(install)
        learn_history(install)
        texts = [row["text"] for row in memory.read("canon")]
        self.assertEqual(texts, ["The user's name is Jordan Ellis."])
        profile_path = install / "state" / "profile.json"
        if profile_path.exists():
            self.assertFalse(json.loads(profile_path.read_text(encoding="utf-8")).get("file_access"))
        user = Path(tempfile.mkdtemp())
        (user / "Projects").mkdir()
        profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else {}
        profile["user_root"] = str(user)
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        block = context_block(install, work_path=str(user))
        self.assertIn("Jordan Ellis", block)
        self.assertIn("Her workspace is always available", block)
        self.assertIn("Projects", block)
        self.assertIn("Directory already read", block)
        self.assertIn("1 name at this one level, all of them: Projects.", block)
        self.assertIn("Not the contents inside those entries.", block)
        self.assertNotIn("roleplay", block.lower())
        self.assertNotIn("Projects", context_block(install))
        note = turn_note(str(user))
        self.assertIn("1 name at this one level, all of them: Projects.", note)
        self.assertIn("Not the contents inside those entries.", note)
        empty = Path(tempfile.mkdtemp())
        self.assertIn("0 names at this one level, all of them: (empty).", turn_note(str(empty)))
        self.assertIn("0 names at this one level, all of them: (empty).", context_block(install, work_path=str(empty)))

    def test_review_runs_on_open_and_leaves_the_prompt(self):
        install = Path(tempfile.mkdtemp())
        memory = Memory(install)
        before = read_prompt("companion")
        now = datetime(2026, 10, 22, 18, 0, tzinfo=timezone.utc)
        memory.add(
            "episodes",
            at=(now - timedelta(hours=2)).isoformat(),
            text="That's wrong, try again.",
            outcome="missed",
        )
        memory.add(
            "episodes",
            at=(now - timedelta(hours=1)).isoformat(),
            text="The patch landed.",
            outcome="done",
            files=["src/app.py"],
        )
        first = on_open(memory, now)
        self.assertTrue(first["ran"])
        self.assertEqual(first["review"]["missed"][0], memory.read("episodes")[0]["id"])
        self.assertEqual(first["review"]["worked"][0], memory.read("episodes")[1]["id"])
        self.assertIn("prompt was not changed", first["review"]["note"])
        self.assertEqual(read_prompt("companion"), before)
        again = on_open(memory, now + timedelta(hours=1))
        self.assertFalse(again["ran"])
        sleeping = on_open(memory, now + timedelta(days=2), background=True, allow_background=False)
        self.assertIn("Background review is off", sleeping["reason"])


if __name__ == "__main__":
    unittest.main()
