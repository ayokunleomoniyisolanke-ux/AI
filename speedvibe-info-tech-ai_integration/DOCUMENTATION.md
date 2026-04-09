# Speedvibe Info Tech — Full documentation

This document describes the **architecture**, **workflows**, **configuration**, and **operations** for the `speedvibe-info-tech-ai_integration` package. For a short folder overview, see [README.md](README.md).

---

## 1. What this integration does

| Capability | Technology |
|------------|------------|
| **Website RAG** | Crawl same-origin pages from the Speedvibe site, chunk text, embed with OpenAI, store in **ChromaDB** (local files on disk). |
| **Text chat** | OpenAI Chat Completions (`OPENAI_CHAT_MODEL`, default `gpt-4o-mini`) with retrieved context appended to the system prompt. |
| **Voice** | **Gemini Live** WebSocket (`/speedvibe/web-call`). **Standalone:** `speedvibe_integration/gemini_voice.py` (set `GEMINI_API_KEY`). **Inside AISA:** uses `app.modules.telephonics.gemini_live` when that package exists. |

**Not used for Speedvibe:** Pinecone (Pinecone is used elsewhere in the parent repo for **LMS** only).

---

## 2. Folder layout

```
speedvibe-info-tech-ai_integration/
├── DOCUMENTATION.md          ← this file
├── README.md
├── .env.example
├── .gitignore
├── requirements.txt
├── app.py                    # Standalone FastAPI (testing)
├── widget/
│   └── speedvibe-chat-voice-widget.html
├── scripts/
│   └── ingest_cli.py
└── speedvibe_integration/
    ├── config.py             # pydantic-settings; loads .env from process cwd
    ├── constants.py          # System prompt for chat + voice
    ├── scraper.py            # BFS crawl, same hostname
    ├── rag_chroma.py         # Chroma + OpenAI embeddings
    ├── chat.py               # POST /speedvibe/chat handler
    ├── gemini_voice.py       # Standalone Gemini Live (voice without monolith)
    ├── schemas.py
    └── router.py             # All HTTP + WebSocket routes
```

**Optional parent repo (AISA backend):**

- `app/main.py` — inserts `speedvibe-info-tech-ai_integration` on `sys.path`, mounts `speedvibe_router` at `API_V1_STR` (e.g. `/api/v1`).
- `app/modules/telephonics/gemini_live.py` — when importable, `/speedvibe/web-call` uses this handler with `assistant="speedvibe"` (otherwise falls back to `gemini_voice.py`).

---

## 3. Environment variables

Copy `.env.example` to **`.env` inside `speedvibe-info-tech-ai_integration`** — `config.py` loads that path by default (works regardless of process cwd). When this package is embedded in AISA, you can instead rely on the **host** `.env` if you inject the same variables into the environment.

| Variable | Required for | Description |
|----------|----------------|-------------|
| `OPENAI_API_KEY` | Chat, embeddings, ingest | OpenAI API key. |
| `SPEEDVIBE_BASE_URL` | Scrape default | Default `https://speedvibeinfotech-hub.com.ng`. |
| `CHROMA_PERSIST_DIR` | RAG | Optional. Default is `chroma_data_speedvibe` under this integration folder (see `config.py`). |
| `OPENAI_CHAT_MODEL` | Chat | Default `gpt-4o-mini`. |
| `OPENAI_EMBEDDING_MODEL` | Embeddings | Default `text-embedding-3-small`. |
| `GEMINI_API_KEY` | Voice | Required for `/speedvibe/web-call` (standalone **or** full backend). Get a key from Google AI Studio / Gemini API. |

**Security:** Never commit `.env` or real keys. `.gitignore` excludes `.env` and Chroma data dirs.

---

## 4. API reference

Base path when mounted: `{API_V1_STR}/speedvibe` (e.g. `/api/v1/speedvibe`).

| Method | Path | Body / query | Response |
|--------|------|--------------|----------|
| POST | `/chat` | `{"message": "..."}` | `{"response": "..."}` |
| POST | `/scrape` | Optional `website_url`, `max_pages` | Job started (background). |
| GET | `/stats` | — | Document counts / Chroma stats. |
| GET | `/search` | `query`, optional `top_k` | Debug search hits. |
| DELETE | `/reset` | — | Clears the Speedvibe Chroma collection (destructive). |
| WebSocket | `/web-call` | Gemini Live binary/text protocol | Voice; needs `GEMINI_API_KEY` and `pip install google-genai`. |

**Example (chat):**

```http
POST /api/v1/speedvibe/chat
Content-Type: application/json

{"message": "What services do you offer?"}
```

---

## 5. Workflows

### 5.1 Develop inside the AISA backend (this repo)

1. Install dependencies: `pip install -r requirements.txt` (root + integration as needed).
2. Set variables in the **root** `.env` (`OPENAI_API_KEY`, optionally `GEMINI_API_KEY`, `CHROMA_PERSIST_DIR`).
3. Start the API (e.g. `uvicorn app.main:app`).
4. Ingest: `POST /api/v1/speedvibe/scrape` or run `python scripts/ingest_cli.py` from `speedvibe-info-tech-ai_integration` with `PYTHONPATH` set.
5. Test chat: `POST /api/v1/speedvibe/chat`.
6. Test voice: widget or WS client to `wss://.../api/v1/speedvibe/web-call`.

### 5.2 Standalone (integration folder only)

Useful for quick tests without the full monolith.

```bash
cd speedvibe-info-tech-ai_integration
copy .env.example .env
# Edit .env — OPENAI_API_KEY; for voice add GEMINI_API_KEY

python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
set PYTHONPATH=.
python scripts/ingest_cli.py --max-pages 20
uvicorn app:app --reload --port 8010
```

- Chat: `POST http://localhost:8010/api/v1/speedvibe/chat`
- **Voice:** Set `GEMINI_API_KEY` in `.env`. Widget `wsBase` → `ws://localhost:8010` (or `wss://` in production). The server uses `gemini_voice.py` when `app.modules.telephonics` is not on the path.

### 5.3 Separate GitHub repo (e.g. `Documents\AI`)

Typical flow when the deliverable is **only** this folder in its own repository:

1. **Clone** the empty (or existing) remote, e.g.  
   `git clone https://github.com/<org>/AI.git`  
   into `Documents\AI` (or any folder).
2. **Copy** the entire `speedvibe-info-tech-ai_integration` directory into that clone (drag-and-drop or `Copy-Item` / `cp -r`). You are **not** required to run `git commit` for the files to exist locally; commit is only when you want history on GitHub.
3. **Optional — first push:**
   ```bash
   cd Documents\AI
   git add speedvibe-info-tech-ai_integration
   git commit -m "Add Speedvibe Info Tech AI integration"
   git branch -M main
   git push -u origin main
   ```
4. **Merge into a FastAPI backend later:** copy the same folder next to the host `app/`, add `sys.path` + `include_router` as in `app/main.py` here.

### 5.4 WordPress / static site embed

1. Open `widget/speedvibe-chat-voice-widget.html`.
2. Find the script block that sets `apiBase`, `wsBase`, and `SVB_CONFIG`.
3. For **production**, set:
   - `apiBase` → `https://<your-api-host>` (no trailing slash on the path; the file appends `/api/v1/speedvibe/chat`).
   - `wsBase` → `wss://<your-api-host>` (same host as HTTPS when possible; appends `/api/v1/speedvibe/web-call`).
4. Replace placeholder hosts like `YOUR-BACKEND.example.com`.
5. Paste the **entire** HTML into a Custom HTML block, or enqueue via theme (ensure the page is **HTTPS** so mixed content does not block `wss://`).

---

## 6. Data and backups

- **Chroma** stores vectors under `CHROMA_PERSIST_DIR` (default `chroma_data_speedvibe/`). This directory is **gitignored** — copy it between servers if you need to preserve the index without re-ingesting.
- **Re-ingest** after major site changes: run scrape/ingest again, or `DELETE /reset` then ingest (use with care).

---

## 7. Troubleshooting

| Symptom | Things to check |
|---------|-------------------|
| 401 / errors from OpenAI | `OPENAI_API_KEY` set and valid; billing enabled. |
| Empty or generic answers | Run ingest; check `GET /stats` > 0; verify `SPEEDVIBE_BASE_URL` and crawl reach real HTML. |
| Chroma permission errors | Writable path for `CHROMA_PERSIST_DIR`; disk space. |
| Voice never connects | Set `GEMINI_API_KEY`; `pip install google-genai`; WebSocket URL uses `wss://` on HTTPS pages; mic permission in browser. |
| `google-genai` errors | Match package version with [Google’s install docs](https://ai.google.dev/); check API key restrictions. |
| `ModuleNotFoundError: speedvibe_integration` | Host must add `speedvibe-info-tech-ai_integration` parent path to `sys.path` before import (see `app/main.py`). |

---

## 8. Related docs

- [README.md](README.md) — short overview and folder tree.
- Parent repo: `WEB_INTEGRATION_README.md`, `QUICKSTART.md` (MacTay / telephonics patterns).

---

## 9. Versioning

Package version is defined in `speedvibe_integration/__init__.py` (`__version__`). Bump when you ship breaking API or config changes.
