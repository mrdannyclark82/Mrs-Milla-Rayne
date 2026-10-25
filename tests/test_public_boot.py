"""The public boot path must not dress house weights or private language."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mrs_public.boot import first_boot
from mrs_public.cortex import choose
from mrs_public.guard import leaks
from mrs_public.models import suggest
from mrs_public.pack import ollama_modelfile, openai_preset, read_prompt
from mrs_public.scan import scan_ollama


class _Body:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _opener(payload):
    def fetch(url, timeout=3):
        return _Body(payload)

    return fetch


HOUSE = [
    "milla-rayne:latest",
    "mrdannyclark82/milla-rayne:latest",
    "devmilla:latest",
    "qwen2.5-coder:7b",
    "gemma2:2b",
    "moondream:latest",
    "nomic-embed-text:latest",
]


class PublicBootTest(unittest.TestCase):
    def test_prompts_have_no_private_words(self):
        for role in ("companion", "code", "vision"):
            self.assertEqual(leaks(read_prompt(role)), [])

    def test_shipped_prose_has_no_private_words(self):
        root = Path(__file__).resolve().parents[1]
        for rel in (
            "README.md",
            "persona/public_mrs.md",
            "persona/roles/code.md",
            "persona/roles/vision.md",
        ):
            text = (root / rel).read_text(encoding="utf-8")
            self.assertEqual(leaks(text), [], rel)

    def test_roles_keep_the_spine(self):
        code = read_prompt("code")
        self.assertIn("dedicated daily driver", code)
        self.assertIn("Engineering first", code)
        vision = read_prompt("vision")
        self.assertIn("dedicated daily driver", vision)
        self.assertIn("Say what is actually in the image", vision)
        self.assertEqual(read_prompt("embed"), "")

    def test_house_tags_are_not_suggested(self):
        picked = suggest(HOUSE)
        self.assertEqual(picked["companion"], "gemma2:2b")
        self.assertEqual(picked["code"], "qwen2.5-coder:7b")
        self.assertEqual(picked["vision"], "moondream:latest")
        self.assertEqual(picked["embed"], "nomic-embed-text:latest")
        self.assertIn("code, coder, or coding", picked["code_reason"])

    def test_coding_in_the_name_is_enough(self):
        picked = suggest(["llama3:8b", "deepseek-coding:latest"])
        self.assertEqual(picked["code"], "deepseek-coding:latest")

    def test_only_house_tags_refuse(self):
        result = first_boot(
            Path(tempfile.mkdtemp()),
            permission=True,
            opener=_opener({"models": [{"name": "milla-rayne:latest"}, {"name": "devmilla:latest"}]}),
        )
        self.assertFalse(result.ok)
        self.assertIn("House weights", result.reason)

    def test_permission_blocks_the_scan(self):
        seen = []

        def fetch(url, timeout=3):
            seen.append(url)
            raise AssertionError("scan ran without permission")

        scan = scan_ollama(permission=False, opener=fetch)
        self.assertFalse(scan.ok)
        self.assertEqual(seen, [])
        self.assertIn("permission", scan.reason)

    def test_auto_writes_modelfiles_and_a_fresh_log(self):
        dest = Path(tempfile.mkdtemp())
        result = first_boot(dest, permission=True, mode="auto", opener=_opener({"models": [{"name": n} for n in HOUSE]}))
        self.assertTrue(result.ok, result.reason)
        companion = (dest / "persona" / "companion.Modelfile").read_text(encoding="utf-8")
        self.assertTrue(companion.startswith("FROM gemma2:2b\n"))
        self.assertIn("Mrs. Milla Rayne", companion)
        self.assertIn("dedicated daily driver", companion)
        self.assertNotIn("FROM milla-rayne", companion)
        code = (dest / "persona" / "code.Modelfile").read_text(encoding="utf-8")
        self.assertTrue(code.startswith("FROM qwen2.5-coder:7b\n"))
        self.assertIn("dedicated daily driver", code)
        self.assertIn("Engineering first", code)
        self.assertEqual(leaks(companion + code), [])
        profile = json.loads((dest / "state" / "profile.json").read_text(encoding="utf-8"))
        self.assertTrue(str(profile["workspace"]).endswith("workspace"))
        self.assertIn("Nothing in here is executed", (dest / "workspace" / "README.md").read_text(encoding="utf-8"))
        truth = (dest / "state" / "truth_events.jsonl").read_text(encoding="utf-8").strip()
        self.assertIn("started empty", truth)
        neuro = json.loads((dest / "state" / "neuro_state.json").read_text(encoding="utf-8"))
        self.assertEqual(neuro["oxytocin"], 0.5)
        intro = (dest / "voice" / "intro.txt").read_text(encoding="utf-8")
        self.assertIn("dedicated daily driver", intro)
        self.assertEqual(leaks(intro), [])
        self.assertEqual(result.volume, 0.55)
        self.assertEqual(result.next_steps, ["lights", "bluetooth", "local_files", "permissions"])

    def test_openai_preset_is_not_a_modelfile(self):
        dest = Path(tempfile.mkdtemp())
        result = first_boot(
            dest,
            permission=True,
            runtime="llama.cpp",
            base_url="http://127.0.0.1:8080/v1",
            opener=_opener({"models": [{"name": "gemma2:2b"}]}),
        )
        self.assertTrue(result.ok, result.reason)
        preset = json.loads((dest / "persona" / "companion.preset.json").read_text(encoding="utf-8"))
        self.assertEqual(preset["format"], "openai-local-preset")
        self.assertEqual(preset["model"], "gemma2:2b")
        self.assertNotIn("FROM ", json.dumps(preset))
        self.assertTrue(openai_preset("code", "gemma2:2b", "http://127.0.0.1:8080/v1")["system"])

    def test_down_ollama_does_not_invent_a_model(self):
        def fetch(url, timeout=3):
            raise OSError("connection refused")

        result = first_boot(Path(tempfile.mkdtemp()), permission=True, opener=fetch)
        self.assertFalse(result.ok)
        self.assertIn("not answering", result.reason)
        self.assertNotIn("grok", result.reason.lower())

    def test_cortex_routes_code_and_keeps_exec_off(self):
        choice = choose("fix this bug in the parser", has_vision=True, has_embed=False, file_access=True)
        self.assertEqual(choice["role"], "code")
        self.assertIn("workspace_read", choice["tools"])
        self.assertIn("workspace_write", choice["tools"])
        self.assertFalse(choice["execute"])
        closed = choose("fix this bug in the parser", has_vision=True, has_embed=False)
        self.assertIn("canvas_write", closed["tools"])
        self.assertIn("download_ready", closed["tools"])
        blocked = choose("exec(open the sandbox)", has_vision=False, has_embed=False)
        self.assertEqual(blocked["sandbox"], "off")
        self.assertIn("canvas", blocked["reason"])

    def test_modelfile_helper_uses_the_chosen_base(self):
        text = ollama_modelfile("companion", "llama3:8b")
        self.assertIn("FROM llama3:8b", text)
        self.assertEqual(leaks(text), [])


if __name__ == "__main__":
    unittest.main()
