# RICA

A self-hosted personal AI assistant. RICA answers from a private Markdown knowledge base, searches and reads the web, and runs on free cloud LLM tiers (Groq, Gemini). A local Qwen model on llama.cpp is the fallback when the cloud tiers are unavailable.

The full design, milestones, and decisions are in [RICA_PLAN.md](RICA_PLAN.md).

## Current stack

| Service | Purpose |
|---|---|
| `llamacpp` | Local Qwen models via llama.cpp server |
| `openwebui` | Chat UI |
| `ngrok` | Public access to Open WebUI |

## Setup

```bash
cp .env.example .env   # fill in values
docker compose up -d
```

GGUF models are read from `/home/siam/models` (see `docker-compose.yml`).

Personal data (owner profile, notes) lives in a separate private repository, never in this one.
