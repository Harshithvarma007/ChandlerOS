# ChandlerOS

A production-engineered conversational AI agent for a personal portfolio — answers questions about the owner's work, projects, research, and writing, grounded strictly in a curated knowledge graph, in a witty, ChandlerOS-flavored voice that's decoupled from any specific LLM provider.

This isn't a portfolio chatbot demo. It's a working system built to demonstrate real production LLM engineering end to end — knowledge graphs, hybrid Graph+Vector RAG, a provider-agnostic LLM gateway with model routing and circuit breakers, personality as an independently controllable layer, grounding and prompt-injection defense, semantic caching, graceful degradation, and an evaluation framework combining deterministic checks with an LLM-as-judge — targeting ~$0/month on free-tier infrastructure.

See [`CHANDLEROS_BLUEPRINT.md`](./CHANDLEROS_BLUEPRINT.md) for the full 59-section architecture specification, and [`plan.md`](./plan.md) for the original design brief.

## Architecture at a glance

```
USER QUERY
    -> Abuse/Rate-Limit Check
    -> Prompt-Injection Check
    -> Query Understanding (deterministic entity/intent resolution, session-aware)
    -> Retrieval Router  ->  Graph RAG | Vector RAG | both
    -> Context Builder (token-budgeted, evidence-tagged)
    -> Personality Policy (context-dependent, model-agnostic)
    -> LLM Gateway -> Model Router -> Provider Adapter (Gemini / Groq)
    -> Grounding + Output Validation  (regenerate once, then strip/fallback)
    -> Structured Response
```

Reliability sits underneath the whole pipeline: retries with backoff, per-provider circuit breakers, request-budget timeouts, multi-layer rate limiting, response/semantic caching, and a Graceful Degradation state machine (NORMAL → DEGRADED → FALLBACK → RECOVERY) that serves hand-written, personality-consistent static responses — never a fabricated answer — when every provider is down.

## Project layout

| Path | What it is |
|---|---|
| `app/` | The running service — retrieval, gateway, personality, reliability, and the FastAPI HTTP layer (`main.py`) |
| `ingestion/` | Offline pipeline that builds the knowledge graph + vector index (`knowledge.db`) from raw sources |
| `Chandleros/` | Derived personality-analysis dataset backing the ChandlerOS voice (see its own license notice below) |
| `CHANDLEROS_BLUEPRINT.md` | Full architecture specification |
| `plan.md` | The original design brief this was built from |

## Running it locally

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp ../.env.example ../.env   # then fill in GEMINI_API_KEY / GROQ_API_KEY

uvicorn main:app --reload
```

Then:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/ask -H "Content-Type: application/json" \
     -d '{"question": "Which projects use Python?"}'
```

`POST /ask/stream` streams the same pipeline over SSE. `GET /stats` returns a request/token/cost rollup; `GET /version` returns the active knowledge/prompt/personality versions.

### Running the checks

```bash
cd app
for f in eval_phase1 eval_phase2 eval_phase3 eval_phase4 eval_phase5 eval_phase6 eval_phase7 eval_phase8 eval_conversation_memory; do
  python $f.py
done
python test_api_smoke.py       # HTTP layer, no live calls
python eval_llm_judge.py       # requires provider keys — skips gracefully without them
```

### Rebuilding the knowledge base

```bash
cd ingestion
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
python build_graph.py     # entities/relationships/evidence -> knowledge.db
python build_chunks.py    # embeddings for vector retrieval -> knowledge.db
```

### Docker

```bash
docker build -t chandleros .
docker run -p 8000:8000 --env-file .env chandleros
```

## License

MIT — see [`LICENSE`](./LICENSE) — with one carve-out: `Chandleros/` contains a dataset derived from copyrighted third-party dialogue and is excluded from that grant. See the NOTICE in `LICENSE` and `Chandleros/dataset_provenance.json` for details.
