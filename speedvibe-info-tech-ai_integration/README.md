# Speedvibe Info Tech — AI integration (drop-in)

Self-contained **RAG (Chroma) + text chat + scrape API + WordPress widget** for
[Speedvibe Info Tech](https://speedvibeinfotech-hub.com.ng). Copy **this entire folder** (`speedvibe-info-tech-ai_integration`) into your backend repo; all Speedvibe-specific assets live here.

**Full guide (architecture, env, API, workflows, Git, WordPress, troubleshooting):** **[DOCUMENTATION.md](DOCUMENTATION.md)**

## Folder layout (everything for this integration)

```
speedvibe-info-tech-ai_integration/
├── DOCUMENTATION.md          ← full workflow & operations
├── README.md                 ← this file
├── .env.example
├── .gitignore
├── requirements.txt
├── app.py                    ← standalone FastAPI (local testing)
├── widget/
│   └── speedvibe-chat-voice-widget.html   ← WordPress / site embed (chat + voice)
├── scripts/
│   └── ingest_cli.py         ← CLI crawl + Chroma ingest
└── speedvibe_integration/    ← Python package
    ├── __init__.py
    ├── config.py
    ├── constants.py
    ├── schemas.py
    ├── scraper.py
    ├── rag_chroma.py
    ├── chat.py
    └── router.py
```

**Also wired in the parent repo (not duplicated here):**

- `app/main.py` — adds `speedvibe-info-tech-ai_integration` to `sys.path` and mounts the router.
- `app/modules/telephonics/gemini_live.py` — `assistant="speedvibe"` for voice RAG.

## What each part does

| Path | Purpose |
|------|---------|
| `speedvibe_integration/` | Scraper, Chroma RAG, chat, FastAPI routes (`/speedvibe/...`) |
| `app.py` | Run alone: `uvicorn app:app` from this directory |
| `scripts/ingest_cli.py` | One-shot crawl + embed |
| `widget/speedvibe-chat-voice-widget.html` | Floating chat + Gemini Live voice; edit `apiBase` / `wsBase` inside the script |

## API (after mount under `/api/v1`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/speedvibe/chat` | JSON `{"message": "..."}` → `{"response": "..."}` |
| POST | `/speedvibe/scrape` | Background scrape + ingest (optional `website_url`, `max_pages`) |
| GET | `/speedvibe/stats` | Chroma document count |
| GET | `/speedvibe/search?query=...` | Debug similarity search |
| DELETE | `/speedvibe/reset` | Clear the collection |
| WebSocket | `/speedvibe/web-call` | Gemini Live voice (full backend + `GEMINI_API_KEY`) |

## Plan (checklist)

1. **Environment** — Copy `.env.example` to `.env`, set `OPENAI_API_KEY`. For voice, set `GEMINI_API_KEY` in the host app (`app/common/config.py`).
2. **Dependencies** — `pip install -r requirements.txt` (merge into host project as needed).
3. **Ingest** — `python scripts/ingest_cli.py` or `POST /speedvibe/scrape`.
4. **Mount router** — See `app/main.py` in the parent repo (path + `include_router`).
5. **Widget** — Use **`widget/speedvibe-chat-voice-widget.html` only** (this folder). Set production `apiBase` (https) and `wsBase` (wss) to your API host so paths end with `/api/v1/speedvibe/chat` and `/api/v1/speedvibe/web-call`.
6. **WordPress** — Custom HTML block: paste the contents of `widget/speedvibe-chat-voice-widget.html`.

## Local run (standalone)

```bash
cd speedvibe-info-tech-ai_integration
copy .env.example .env
# edit .env — OPENAI_API_KEY required

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set PYTHONPATH=.
python scripts/ingest_cli.py --max-pages 20
uvicorn app:app --reload --port 8010
```

Chat: `POST http://localhost:8010/api/v1/speedvibe/chat` with `{"message":"Hello"}`.

**Voice:** Standalone `app.py` has no `gemini_live`; WebSocket returns until this package is used inside the main backend.

## Merge into another FastAPI app

1. Copy the whole `speedvibe-info-tech-ai_integration` directory next to your `app/` package.
2. Prepend that directory to `sys.path` at startup (same pattern as `app/main.py` here).
3. `from speedvibe_integration.router import router as speedvibe_router` and `app.include_router(speedvibe_router, prefix="/api/v1")`.
4. Set `OPENAI_API_KEY` in host `.env`. Optionally `CHROMA_PERSIST_DIR=./speedvibe-info-tech-ai_integration/chroma_data_speedvibe` when running from repo root.

## RAG source

Default scrape URL: `https://speedvibeinfotech-hub.com.ng` (`SPEEDVIBE_BASE_URL` or scrape body).

## Chroma data

Default: `chroma_data_speedvibe/` (gitignored). Back up when moving servers.
