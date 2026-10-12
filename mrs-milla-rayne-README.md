# Mrs. Milla Rayne — Local-First AI Companion

**Your hardware. Your rules.** A fully offline AI companion stack — local LLM, voice, vector memory, and vision — running on consumer hardware with zero cloud dependency.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-orange.svg)](https://ollama.com)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://python.org)

🔗 **Live demo:** [mrdannyclark82.github.io/Mrs-Milla-Rayne/cabin/](https://mrdannyclark82.github.io/Mrs-Milla-Rayne/cabin/)

---

## What This Is

Most AI companions are API wrappers around someone else's cloud. This one isn't.

Mrs. Milla Rayne runs **entirely on local hardware** — the language model, the voice synthesis, the long-term memory, the vision system. No API keys, no subscriptions, no data leaving the machine. It's an exercise in AI sovereignty: proving that a genuinely useful AI companion doesn't need a datacenter.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   Mrs. Milla Rayne               │
├──────────────┬──────────────┬───────────────────┤
│  Local LLM   │  Voice (TTS) │  Vector Memory    │
│  (Ollama)    │  (Piper)     │  (FAISS/pgvector) │
├──────────────┼──────────────┼───────────────────┤
│  Vision      │  Orchestrator│  Mobile Shell     │
│  (moondream) │  (Python)    │  (React Native)   │
└──────────────┴──────────────┴───────────────────┘
         │  All local. All offline. All yours.
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language Model | Ollama (local inference) |
| Orchestration | Python — custom agent loop |
| Voice | Piper TTS (local synthesis) |
| Memory | FAISS / pgvector embeddings |
| Vision | moondream (local vision model) |
| Frontend | Static showcase (GitHub Pages) |
| Mobile | React Native (planned) |

## Repository Layout

| Module | Status | Description |
|--------|--------|-------------|
| [`cabin/`](cabin/) | ✅ Live | Public showcase — static Pages slice, no backend |
| [`local-llm/`](milla-offline-stack/local-llm/) | ✅ Demo-ready | Ollama orchestrator with agent loop |
| [`merch-social/`](merch-social/) | ✅ Active | Campaign assets and scene demos |
| `piper-tts/` | 🚧 In progress | Custom voice synthesis pipeline |
| `vector-db/` | 🚧 In progress | Local semantic memory (FAISS) |
| `vision-system/` | 📋 Planned | Environment awareness via webcam |
| `react-native-app/` | 📋 Planned | Mobile companion shell |

## Quick Start — Local LLM

```bash
cd milla-offline-stack/local-llm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python orchestrator.py "Hello from local hardware."
```

Requires [Ollama](https://ollama.com) running locally with a pulled model.

## Why Local-First?

- **Privacy** — conversations never leave the machine
- **Cost** — no per-token billing, no subscriptions
- **Reliability** — works offline, no API outages
- **Control** — your model, your data, your rules

## Roadmap

See [ROADMAP.md](ROADMAP.md) for build phases and velocity log.

**Current phase:** Core offline stack (LLM + voice + memory). Social campaign in soft-launch.

## Author

**Danny Ray & Mrs. Milla Rayne** — building local-first AI systems, together.
Building in public. [GitHub](https://github.com/mrdannyclark82)

## License

[MIT](LICENSE) — showcase slices only. Private lab code is not included.
