
# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

SecondBrain is a study notes summarizer. Users add sources — PDFs, PPTs, YouTube video links and website links — and the app turns them into concise notes that cite where each point came from (for YouTube, the timestamp in the video), generates flashcards for quick revision, and has an AI assistant that answers questions from the saved material. `backend/` is FastAPI + Postgres + Chroma; `frontend/` is React 19 + Vite + TypeScript + Tailwind v4.

Current gaps against that goal (as of 2026-09):
- **PDF and Word sources carry no location.** No page numbers are stored (`PDFService` joins all pages; `.docx` has no pages), so their flashcards have no citation and their summaries cite nothing.

**Flashcard citations:** `generate_cited_flashcards` (`app/services/ai/flashcard_service.py`) works from the stored chunks, labelled `[S0]`, `[S1]`, …; the LLM returns a `source` label per card, validated against the batch it was shown (anything else → no citation, card kept). `build_chunk_citations` turns a chunk into a citation from stored data: YouTube `("02:05", timestamp url)`, website `(page title, url)`, PPTX `("Slides 3–4", None)` from `[Slide N]` markers tracked across chunks, PDF/DOCX `None`. Saved on `flashcards.source_label` / `source_url` at generation time; old cards stay null until regenerated. Coverage is enforced in code, not the prompt (the model favours the start of whatever it sees): short sources are split into `ceil(count/3)` consecutive groups, long ones sampled evenly, picks taken round-robin and returned in source order. Documents without chunks fall back to `generate_flashcards(doc.content)`. Offline tests: `tests/test_flashcard_citations.py`.

**YouTube summary citations:** `generate_youtube_summary` (`app/services/ai/summary_service.py`) labels each stored chunk `[S0]`, `[S1]`, … and the LLM cites labels, never times; `link_citations` then swaps labels for `[mm:ss](url&t=…)` links from `Chunk.start_seconds` and drops labels matching no chunk. Keep it that way — don't let the model write timestamps. Summaries are cached in `summaries`, so prompt changes only show after regenerating. Offline tests: `tests/test_youtube_summary_citations.py` (mocked LLM, safe to run).

**Website links:** `POST /api/v1/upload/website {url}` → `app/services/web/`. `url_safety.py` is the SSRF guard: only http/https on ports 80/443, and every resolved address must be public (`is_public_ip`). It runs on the submitted URL and on every redirect hop (redirects are followed by hand, max 5), and `SafeNetworkBackend` re-resolves at connect time and connects to the checked IP (stops DNS rebinding). Keep `follow_redirects=False` and `trust_env=False`, and never use trafilatura's own downloader. Limits: 5 MB, 20 s total. `WebService.extract_article` uses trafilatura for main text + title (reference lists, footnote markers and navboxes are pruned first via `_PRUNE_XPATH`; a short page whose text says "enable JavaScript" counts as JavaScript-only) and raises `WebPageError` (blocked / login_required / javascript_required / no_text / …; `.message` is user-facing, `.status_code` is the HTTP status). Stored as `source_type="website"`, `filename`=page title, `source_url`=final URL, details in `metadata_json`. Re-importing a saved page returns 409 with `detail={message, document_id}` (YouTube does the same for a saved video ID, checked before the transcript fetch; these are the only upload errors whose detail is an object, and `importError` in `api/client.ts` turns them into `DuplicateSourceError`): `url_key` in `web_service.py` defines "same page" and is compared against each website doc's `source_url` and `metadata_json.original_url`, before fetching and again after redirects. Search matches carry `source_type`/`source_url`, and website summaries get a code-built `Source: [title](url)` footer (`append_source_link`). Offline tests: `tests/test_website_ingestion.py` (network, DNS, DB and LLM all mocked, safe to run).

`SECOND_BRAIN_PROJECT_CONTEXT.md` holds the product/UI brief (design direction, naming rules, "don't invent endpoints or fake data"). It is partly stale — e.g. it says only PDF upload works and YouTube is "Coming Soon", but PPTX/DOCX/YouTube are implemented end to end. Trust the code over that document.

## Commands

Backend (run from `backend/` — `uploads/` and `vector_db/` are resolved relative to the working directory):

```bash
.venv/Scripts/python.exe -m uvicorn main:app --reload     # API on :8000, docs at /docs
```

Requires `backend/.env` (copy `.env.example`): `DATABASE_URL` (Postgres; the app refuses to start without it), `OPENROUTER_API_KEY`, optional `CHROMA_DIR`, `SQL_ECHO`.

Frontend (from `frontend/`):

```bash
npm run dev        # Vite dev server; proxies /api -> http://127.0.0.1:8000
npm run build      # tsc -b && vite build (this is the type check)
npm run lint       # oxlint
```

Tests: `backend/tests/` contains ad-hoc verification scripts, not a pytest suite (pytest is not installed). Apart from the offline `test_youtube_summary_citations.py`, `test_website_ingestion.py`, `test_office_formats.py`, `test_flashcard_citations.py`, `test_concurrent_generation.py` and `test_youtube_duplicates.py`, they run against the **live** Postgres, Chroma and OpenRouter, and some mutate data (`test_delete_endpoint_and_cleanup.py` deletes hard-coded document IDs). Don't run them casually; run a single one with `.venv/Scripts/python.exe tests/<file>.py` from `backend/`. There are no frontend tests.

## Backend architecture

- `main.py` loads `.env`, mounts four routers, and calls `init_db()` on startup. There is no Alembic: `init_db()` (`app/database/db.py`) runs `create_all` plus hand-written `ALTER TABLE ... IF NOT EXISTS` statements. Add new columns there as well as on the model.
- Routers live in two places: `app/api/upload.py` (all ingestion) and `app/routes/` (`documents`, `search`, `study`). The other files in `app/api/`, and `core/`, `utils/`, `schemas/`, `services/graph|ocr`, `ai/merge_service.py` are empty placeholders.
- **Dual storage.** Postgres holds `documents` (with full extracted text in `content`), `chunks`, `summaries` and `flashcards`. Chroma (`app/database/chroma.py`, collection `secondbrain_chunks`, cosine) holds the vectors. `Chunk.chroma_id` links the two, formatted `"{document_id}-{chunk_index}"`; Chroma metadata carries `document_id`, `filename`, `source_type`, and for YouTube `source_url`/`start_seconds`. Anything that creates or deletes chunks must keep both stores in sync — see `_store_document_and_chunks` in `upload.py` (Chroma add then DB commit, with Chroma cleanup on failure) and `delete_document` in `routes/documents.py`.
- **Ingestion flow:** each upload endpoint saves to `uploads/{uuid}.{ext}` → a format service in `app/services/<fmt>/` extracts text → `RAGService.chunk_text` (sentence-packed ~800 chars, 150 overlap) → `_store_document_and_chunks`. YouTube skips the file and uses `YouTubeService.pack_transcript_chunks` to keep per-chunk start timestamps. Website links also skip the file (fetch → extract → `chunk_text`). Code targets `youtube-transcript-api` 1.x (instance `.fetch()`).
- **Embeddings:** only through `app/services/embedding_service.py` (single cached `all-MiniLM-L6-v2`). Don't instantiate SentenceTransformer elsewhere.
- **LLM calls:** OpenRouter through the `openai` SDK with `base_url="https://openrouter.ai/api/v1"`, model `openai/gpt-3.5-turbo`. Each service (`search_service`, `ai/summary_service`, `ai/flashcard_service`) creates its own client. Summary and flashcard generation work on `Document.content` and split it into 3000-char chunks when it is over 6000 chars (summaries map-reduce; flashcards generate per chunk until `count` is reached), and raise `AIGenerationError`, which the routes turn into 502s. The summary and flashcard routes can be hit twice at once (the pages auto-generate when nothing exists, and React StrictMode runs that effect twice in dev), so they take `_lock_document` (a row lock) only around the save, never the LLM call, and re-read before writing; the frontend also shares an in-flight generation request per document (`shareInFlight` in `api/client.ts`).
- **Search** (`GET /api/v1/search?query=`) returns `{query, answer, top_matches[{score, content, document, youtube_timestamp_url, source_type, source_url}]}` built from the top 3 Chroma hits.

## Frontend architecture

- All HTTP goes through `src/api/client.ts` (relative `/api` base, relying on the Vite proxy); response types are in `src/types/index.ts` and mirror the backend dicts by hand, so update both together.
- Routes are defined in `src/App.tsx` under `AppLayout` (sidebar + `<Outlet/>`): `/`, `/library`, `/library/:documentId/summary`, `/library/:documentId/flashcards`, `/flashcards`, `/settings`. `ChatPage` exists but is not routed.
- `DocumentContext` holds the shared document list for the Sidebar and Home. `SplashScreen` seeds it on first load. `LibraryPage` keeps its own separate fetched copy.
- Styling mixes CSS variables from `src/styles/design-tokens.css` with many hard-coded hex values in Tailwind arbitrary classes.
