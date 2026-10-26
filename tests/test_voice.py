"""Voice: XTTS v2, the install's clip and engine, never shipped here.
Availability is reported plainly; synthesis is testable with a fake
engine; the speak endpoint refuses while the toggle is off."""

from __future__ import annotations

import io
import json
import tempfile
import threading
import unittest
import wave
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

from mrs_public import voice
from mrs_public.voice import _wav_bytes, synthesize_reply, voice_status
from mrs_public.view import ensure_install, serve, state, update_profile


class FakeEngine:
    def __init__(self):
        self.calls = []

    def synthesize(self, text, speaker_wav):
        self.calls.append((text, Path(speaker_wav).name))
        return b"FAKE-WAV"


def install_with_reference() -> Path:
    install = ensure_install(Path(tempfile.mkdtemp()))
    (install / "state" / "voice_reference.wav").write_bytes(b"RIFF-fake")
    return install


class VoiceStatusTest(unittest.TestCase):
    def test_no_reference_is_the_first_reason(self):
        install = ensure_install(Path(tempfile.mkdtemp()))
        status = voice_status(install)
        self.assertFalse(status["available"])
        self.assertFalse(status["reference"])
        self.assertIn("reference clip", status["reason"])

    def test_reference_without_engine_is_the_second_reason(self):
        install = install_with_reference()
        with mock.patch.object(voice, "_tts_spec", return_value=None):
            status = voice_status(install)
        self.assertFalse(status["available"])
        self.assertTrue(status["reference"])
        self.assertIn("coqui-tts", status["reason"])

    def test_reference_and_engine_is_available(self):
        install = install_with_reference()
        with mock.patch.object(voice, "_tts_spec", return_value=object()):
            status = voice_status(install)
        self.assertTrue(status["available"])
        self.assertEqual(status["reason"], "")


class SynthesizeTest(unittest.TestCase):
    def test_speaks_with_fake_engine(self):
        install = install_with_reference()
        engine = FakeEngine()
        audio = synthesize_reply(install, "Hello `there`.", engine=engine)
        self.assertEqual(audio, b"FAKE-WAV")
        self.assertEqual(engine.calls, [("Hello there.", "voice_reference.wav")])

    def test_refusals_are_plain(self):
        install = install_with_reference()
        with self.assertRaises(ValueError):
            synthesize_reply(install, "   ", engine=FakeEngine())
        with self.assertRaises(ValueError):
            synthesize_reply(install, "x" * 1300, engine=FakeEngine())
        bare = ensure_install(Path(tempfile.mkdtemp()))
        with self.assertRaises(ValueError):
            synthesize_reply(bare, "Hello.", engine=FakeEngine())

    def test_wav_bytes_are_real_wav(self):
        raw = _wav_bytes([0.0, 1.0, -1.0, 0.5])
        with wave.open(io.BytesIO(raw), "rb") as wav:
            self.assertEqual(wav.getframerate(), 24000)
            self.assertEqual(wav.getnchannels(), 1)
            self.assertEqual(wav.getsampwidth(), 2)
            self.assertEqual(wav.getnframes(), 4)


class SpeakEndpointTest(unittest.TestCase):
    def setUp(self):
        self.install = install_with_reference()
        self.engine = FakeEngine()
        self.server = serve(self.install, 0, voice_engine=self.engine)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post_speak(self, text: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request(
            "POST",
            "/api/speak",
            body=json.dumps({"text": text}),
            headers={"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, resp.getheader("Content-Type"), body

    def test_refuses_while_toggle_off(self):
        status, _, body = self.post_speak("Hello.")
        self.assertEqual(status, 400)
        self.assertIn("Voice is off", body.decode())

    def test_speaks_when_on(self):
        update_profile(self.install, {"voice_enabled": True})
        status, content_type, body = self.post_speak("Hello there.")
        self.assertEqual(status, 200)
        self.assertEqual(content_type, "audio/wav")
        self.assertEqual(body, b"FAKE-WAV")
        snapshot = state(self.install)
        self.assertTrue(snapshot["voice_enabled"])
        self.assertTrue(snapshot["voice"]["reference"])


if __name__ == "__main__":
    unittest.main()
