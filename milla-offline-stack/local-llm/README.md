# Local LLM Orchestrator

Thin Ollama client for offline-first inference. No cloud API required.

## Quick demo (30 seconds)

```bash
cd milla-offline-stack/local-llm
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # optional — defaults to localhost:11434

# Ensure Ollama is running, then:
python orchestrator.py "What runs when the internet doesn't?"
```

## Requirements

- [Ollama](https://ollama.com) running locally (`ollama serve`)
- Python 3.11+
- A pulled model (default: `gemma2:2b`)

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `DEFAULT_MODEL` | `gemma2:2b` | Model for generation |

## What this is

- Health check against local Ollama
- Auto-pull if model missing
- Single-shot `generate()` for scripts and automation

## What this is not (yet)

- Streaming UI, memory, or persona injection — those live in the private stack
- Production deployment guide — showcase slice only