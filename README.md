# RICA

A self-hosted personal AI assistant. RICA answers from a private Markdown knowledge base, searches and reads the web, and runs on free cloud LLM tiers (Groq, Gemini). A local Qwen model on llama.cpp is the fallback when the cloud tiers are unavailable.

The full design, milestones, and decisions are in [RICA_PLAN.md](RICA_PLAN.md).

## Stack

| Service | Purpose | Exposure |
|---|---|---|
| `openwebui` | Chat UI; model `rica` is the default | `:3002` + ngrok |
| `ngrok` | Public access to Open WebUI | public |
| `litellm` | Single model endpoint: Groq, Gemini, local, and `rica` | `127.0.0.1:4000` |
| `rica` | The agent (`rica/`): planner, notes, web, links, cited answers | internal |
| `rica-ingest` | Pulls the knowledge repo every 120 s and indexes it into Qdrant | none |
| `qdrant` | Hybrid (dense + BM25) index of the notes | internal |
| `searxng` | Web search for the agent | internal |
| `llamacpp` | Local Qwen model, the last-resort fallback | `127.0.0.1:8081` |

## Setup

```bash
cp .env.example .env   # fill in values; generate keys with: openssl rand -hex 32
# secrets/rica_deploy_key + secrets/known_hosts: read-only deploy key for the knowledge repo
docker compose up -d
```

## Operations

```bash
docker logs -f rica | grep '"event"'          # one JSON line per request: routes, tier, evidence, latency
docker logs -f rica-ingest                     # sync/index results
docker exec rica python eval/run_eval.py       # eval set (rica/eval/questions.yaml)
docker exec rica-ingest python -m rica.retrieval.store "query"   # debug note search
cd rica && uv run pytest -q                    # unit tests
```

After changing code: `docker compose build rica && docker compose up -d rica rica-ingest`.

GGUF models are read from `/home/siam/models` (see `docker-compose.yml`).

Personal data (owner profile, notes) lives in a separate private repository, never in this one.
