"""Providers: Ollama is built in; OpenAI-compatible servers are the
install's to add. Locality is read off the URL, and image turns never
leave the local Ollama vision path."""

from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path

from mrs_public.chat import stream_chat
from mrs_public.providers import Provider, find_provider, load_providers
from mrs_public.scan import scan_openai
from mrs_public.view import ensure_install, state

PNG_1PX = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAwMCAO+ip1sAAAAASUVORK5CYII="
    )
).decode()


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


def sse_opener(captured: dict, text: str = "Hello there"):
    def fetch(req, timeout=180):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode())
        lines = (
            'data: {"choices": [{"delta": {"content": "Hello "}}]}\n'
            'data: {"choices": [{"delta": {"content": "there"}}]}\n'
            "data: [DONE]\n"
        )
        return Body(lines.encode())

    return fetch


class LoadProvidersTest(unittest.TestCase):
    def test_defaults_to_ollama_only(self):
        providers = load_providers({})
        self.assertEqual([p.id for p in providers], ["ollama"])
        self.assertTrue(providers[0].local)

    def test_profile_entries_and_locality(self):
        profile = {
            "providers": [
                {"kind": "openai", "url": "http://127.0.0.1:8080/v1", "label": "llama.cpp"},
                {"kind": "openai", "url": "https://models.example.com/v1", "label": "Far Away"},
                {"kind": "bogus", "url": "http://127.0.0.1:9/v1", "label": "Nope"},
                {"kind": "openai", "url": "", "label": "No URL"},
            ]
        }
        providers = load_providers(profile)
        self.assertEqual([p.id for p in providers], ["ollama", "llama-cpp", "far-away"])
        self.assertTrue(providers[1].local)
        self.assertFalse(providers[2].local)
        self.assertEqual(find_provider(profile, "far-away").label, "Far Away")
        self.assertIsNone(find_provider(profile, "nope"))


class ScanOpenAITest(unittest.TestCase):
    def test_lists_model_ids(self):
        def fetch(url, timeout=3):
            self.assertTrue(url.endswith("/v1/models"))
            return Body(json.dumps({"data": [{"id": "local"}, {"id": "gguf-1"}]}).encode())

        scan = scan_openai("http://127.0.0.1:8080/v1", permission=True, opener=fetch)
        self.assertTrue(scan.ok)
        self.assertEqual(scan.models, ("local", "gguf-1"))

    def test_permission_first(self):
        scan = scan_openai("http://127.0.0.1:8080/v1", permission=False)
        self.assertFalse(scan.ok)


class OpenAIChatTest(unittest.TestCase):
    def setUp(self):
        self.install = ensure_install(Path(tempfile.mkdtemp()))

    def test_streams_and_reports_provider(self):
        captured: dict = {}
        provider = Provider("llama-cpp", "openai", "http://127.0.0.1:8080/v1", "llama.cpp")
        rows = list(
            stream_chat(
                self.install,
                text="Say hello",
                model="local",
                provider=provider,
                opener=sse_opener(captured),
            )
        )
        tokens = "".join(r.get("token", "") for r in rows)
        done = rows[-1]
        self.assertEqual(tokens, "Hello there")
        self.assertTrue(captured["url"].endswith("/v1/chat/completions"))
        self.assertNotIn("options", captured["payload"])
        self.assertEqual(captured["payload"]["temperature"], 0.7)
        self.assertEqual(done["provider"], "llama.cpp")
        self.assertTrue(done["local"])

    def test_remote_provider_is_not_called_local(self):
        captured: dict = {}
        provider = Provider("far-away", "openai", "https://models.example.com/v1", "Far Away")
        rows = list(
            stream_chat(
                self.install,
                text="Say hello",
                model="whatever",
                provider=provider,
                opener=sse_opener(captured),
            )
        )
        self.assertFalse(rows[-1]["local"])
        self.assertEqual(rows[-1]["provider"], "Far Away")

    def test_image_turn_stays_on_ollama_vision(self):
        def scan_fetch(url, timeout=3):
            return Body(json.dumps({"models": [{"name": "moondream:latest"}]}).encode())

        def chat_fetch(req, timeout=180):
            self.assertTrue(req.full_url.endswith("/api/chat"), req.full_url)
            payload = json.loads(req.data.decode())
            self.assertEqual(payload["model"], "moondream:latest")
            return Body(b'{"message": {"content": "A dot."}, "done": true}\n')

        provider = Provider("llama-cpp", "openai", "http://127.0.0.1:8080/v1", "llama.cpp")
        rows = list(
            stream_chat(
                self.install,
                text="What is this?",
                model="local",
                provider=provider,
                image={"type": "image/png", "data": PNG_1PX},
                scan_opener=scan_fetch,
                opener=chat_fetch,
            )
        )
        done = rows[-1]
        self.assertTrue(done["vision"])
        self.assertEqual(done["model"], "moondream:latest")
        self.assertEqual(done["provider"], "Ollama")
        self.assertTrue(done["local"])


class StateProvidersTest(unittest.TestCase):
    def test_state_lists_provider_models(self):
        install = ensure_install(Path(tempfile.mkdtemp()))
        profile_path = install / "state" / "profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["scan_allowed"] = True
        profile["providers"] = [
            {"kind": "openai", "url": "http://127.0.0.1:8080/v1", "label": "llama.cpp"}
        ]
        profile_path.write_text(json.dumps(profile), encoding="utf-8")

        def fetch(url, timeout=3):
            if url.endswith("/api/tags"):
                return Body(json.dumps({"models": [{"name": "gemma2:2b"}]}).encode())
            if url.endswith("/v1/models"):
                return Body(json.dumps({"data": [{"id": "local"}]}).encode())
            raise AssertionError(url)

        snapshot = state(install, scan_opener=fetch)
        self.assertEqual(snapshot["models"], ["gemma2:2b"])
        self.assertEqual(len(snapshot["provider_models"]), 1)
        entry = snapshot["provider_models"][0]
        self.assertEqual(entry["id"], "llama-cpp")
        self.assertEqual(entry["models"], ["local"])
        self.assertTrue(entry["local"])


if __name__ == "__main__":
    unittest.main()
