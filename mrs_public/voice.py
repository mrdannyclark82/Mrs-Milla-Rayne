"""Her voice, made on this machine: XTTS v2 through the optional
coqui-tts package, cloning the install's own reference clip.

Nothing about a voice ships in this build — no clip, no weights. The
install supplies a few seconds of reference audio at
``state/voice_reference.wav`` (or ``.mp3``), and the engine package is
the install's to add (``pip install coqui-tts``). Without either, voice
is off and the app says why, in plain words.
"""

from __future__ import annotations

import importlib.util
import io
import struct
import wave
from pathlib import Path

MODEL_ID = "tts_models/multilingual/multi-dataset/xtts_v2"
SAMPLE_RATE = 24000  # XTTS v2 speaks at 24 kHz.
MAX_SPEAK_CHARS = 1200
REFERENCE_NAMES = ("voice_reference.wav", "voice_reference.mp3")


def _tts_spec():
    """The engine package's presence, checked without importing it."""
    return importlib.util.find_spec("TTS")


def reference_path(install: Path) -> Path | None:
    state = Path(install) / "state"
    for name in REFERENCE_NAMES:
        path = state / name
        if path.is_file():
            return path
    return None


def voice_status(install: Path) -> dict:
    if reference_path(install) is None:
        return {
            "available": False,
            "engine": "xtts-v2",
            "reference": False,
            "reason": "Voice needs a reference clip: a few seconds of audio at state/voice_reference.wav in the install.",
        }
    if _tts_spec() is None:
        return {
            "available": False,
            "engine": "xtts-v2",
            "reference": True,
            "reason": "Voice needs the XTTS engine on this machine: pip install coqui-tts.",
        }
    return {"available": True, "engine": "xtts-v2", "reference": True, "reason": ""}


def _wav_bytes(samples) -> bytes:
    """Float samples in [-1, 1] to a 16-bit mono WAV, stdlib only."""
    frames = bytearray()
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample)))
        frames += struct.pack("<h", int(value * 32767))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


class XttsEngine:
    """Lazy on purpose: the weights (about 1.8 GB) load on first use and
    stay warm after. The first load may ask the machine's owner to accept
    Coqui's license terms once — the app never accepts them for anyone."""

    def __init__(self) -> None:
        self._tts = None

    def synthesize(self, text: str, speaker_wav: Path, language: str = "en") -> bytes:
        if self._tts is None:
            from TTS.api import TTS

            self._tts = TTS(MODEL_ID)
        samples = self._tts.tts(text=text, speaker_wav=str(speaker_wav), language=language)
        return _wav_bytes(samples)


_DEFAULT_ENGINE: XttsEngine | None = None


def _default_engine() -> XttsEngine:
    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = XttsEngine()
    return _DEFAULT_ENGINE


def _clean(text: str) -> str:
    """What gets spoken: the reply's words, markdown marks off."""
    lines = []
    for line in (text or "").splitlines():
        if line.strip().startswith("```"):
            continue
        lines.append(line.replace("`", ""))
    return " ".join(" ".join(lines).split())


def synthesize_reply(install: Path, text: str, *, engine=None) -> bytes:
    """Speak one reply; return WAV bytes. A refusal is a plain sentence."""
    clean = _clean(text)
    if not clean:
        raise ValueError("There is nothing to speak yet.")
    if len(clean) > MAX_SPEAK_CHARS:
        raise ValueError("That reply is too long to speak whole. Ask for a shorter one.")
    reference = reference_path(install)
    if reference is None:
        raise ValueError(
            "She has no reference clip to speak with. Put a few seconds of voice at "
            "state/voice_reference.wav in the install."
        )
    speaker = engine if engine is not None else _default_engine()
    try:
        return speaker.synthesize(clean, reference)
    except ImportError:
        raise ValueError(
            "The XTTS engine is not installed on this machine: pip install coqui-tts."
        ) from None
    except Exception as exc:  # noqa: BLE001 — the page has to say what failed
        raise ValueError(f"The voice engine did not answer. {type(exc).__name__}: {exc}") from None
