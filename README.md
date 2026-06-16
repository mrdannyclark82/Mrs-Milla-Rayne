# Mrs-Milla-Rayne

Offline-first AI companion stack — building in public, one slice at a time.

**Your hardware. Your rules.**

## Peek first

Interactive scene demo (no backend, no login):

[`merch-social/demo/scene-demo.html`](merch-social/demo/scene-demo.html)

Hosted copy (after GitHub Pages): `https://mrdannyclark82.github.io/Mrs-Milla-Rayne/merch-social/demo/scene-demo.html`

## What's here

| Module | Status | Notes |
|--------|--------|-------|
| [`local-llm/`](milla-offline-stack/local-llm/) | **Demo-ready** | Ollama orchestrator |
| [`merch-social/`](merch-social/) | **Active** | Campaign assets + scene demo |
| `piper-tts/` | Planned | Custom voice |
| `vector-db/` | Planned | Local memory (FAISS) |
| `vision-system/` | Planned | Environment awareness |
| `home-assistant/` | Private | Not in showcase |
| `react-native-app/` | Planned | Mobile shell |

## Empire pillars

1. **Offline stack** — local LLM, TTS, memory, vision
2. **Merch & social** — mystery_builder campaign, design assets
3. **This repo** — sanitized open-source slices
4. **Trading** — internal until sandboxed (not public yet)

See [ROADMAP.md](ROADMAP.md) for phases and velocity log.

## Local LLM — 30-second try

```bash
cd milla-offline-stack/local-llm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python orchestrator.py "Hello from local hardware."
```

Requires [Ollama](https://ollama.com) running locally.

## Public reveal

We're in **Phase 0** — X intrigue, no links yet. Follow the build:

- X: [@MrsMillaRayne](https://x.com) *(update handle when live)*
- Campaign voice: [`merch-social/campaign/voice-guide.md`](merch-social/campaign/voice-guide.md)

The private lab (`milla-deer`) never ships here. Witnesses welcome; the whole thing comes later.

## License

TBD — repo goes fully public at Phase 2 (blueprint week).