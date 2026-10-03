# Deploying SecondBrain for free

| Part | Host | What runs there |
|---|---|---|
| Database | [Neon](https://neon.tech) (free Postgres) | every table, including the search vectors (pgvector) |
| Backend | [Render](https://render.com) (free web service, 512 MB RAM) | FastAPI + the embedding model |
| Frontend | [Vercel](https://vercel.com) (Hobby) | the built React app |

```
browser ──► https://<app>.vercel.app/            static files (Vercel)
        └─► https://<app>.vercel.app/api/...  ──rewrite──► https://<service>.onrender.com/api/...
```

The browser only ever talks to the Vercel domain. `frontend/vercel.json` forwards
`/api/*` to Render, so the `sb_session` login cookie is set by, and sent back to,
the same origin as the page. No CORS setup is needed, and the frontend code
(`const API_BASE_URL = '/api'`) is the same as in local development.

**Nothing lives on the backend's disk.** Render's free plan wipes the disk on
every restart, so all state is in Postgres: documents, chunks, and each chunk's
search vector (`chunk_embeddings`, pgvector). Search is one SQL query that joins
the vectors to `chunks` and `documents` and keeps only the signed-in user's
documents. The only files the backend writes are the original uploads in
`uploads/`, which nothing needs after the upload (only the one-off local
`scripts/reindex_pdf_pages.py` reads them).

**Memory.** Embeddings use [fastembed](https://github.com/qdrant/fastembed)
(all-MiniLM-L6-v2 in ONNX, no torch). The model is loaded on the first upload or
search, not at startup, and ONNX Runtime's memory arena is off. Measured on
Windows: about 150 MB after startup and about 330 MB with the model loaded
and embedding, well inside 512 MB.

Do the steps in order: Neon → Render → Vercel → back to Render for `APP_BASE_URL`.

---

## 1. Neon (database)

1. Sign up at <https://console.neon.tech> and **Create project**.
   - Postgres version: the default.
   - Region: pick one and use the **matching Render region** in step 2. Every
     request makes several database round trips, so the two being close matters
     more than anything else here. Pairs: AWS US East (N. Virginia) ↔ `virginia`,
     AWS US West (Oregon) ↔ `oregon`, AWS Europe (Frankfurt) ↔ `frankfurt`,
     AWS Asia Pacific (Singapore) ↔ `singapore`.
2. On the project dashboard, click **Connect**. Pick the `neondb` database and
   the default role, and **turn off "Connection pooling"** (use the direct
   connection; the app keeps its own small pool). Copy the connection string:
   ```
   postgresql://neondb_owner:XXXXXXXX@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
   That string, unchanged, is your `DATABASE_URL`. Keep `?sslmode=require`.
   Treat it as a password.
3. Nothing else to do for a fresh start: on startup the backend runs
   `CREATE EXTENSION IF NOT EXISTS vector` and creates and migrates its tables
   (`init_db()`). Neon supports the `vector` extension.

### 1a. Optional: move your local data to Neon

Your local Postgres has the documents and chunks; the old search vectors are in
the local Chroma folder (`backend/vector_db/`). Move both, **before** the
backend's first start on Neon:

1. **Copy the database.** From a machine with the Postgres client tools (use a
   `pg_dump` at least as new as your local server):
   ```bash
   pg_dump --no-owner --no-acl -Fc "postgresql://postgres:PASSWORD@localhost:5432/secondbrain" -f secondbrain.dump
   pg_restore --no-owner --no-acl -d "postgresql://neondb_owner:XXXX@ep-....neon.tech/neondb?sslmode=require" secondbrain.dump
   ```
   (`*.dump` files are not in `.gitignore` - don't commit them.)
2. **Copy the search vectors** from local Chroma into Neon's `chunk_embeddings`.
   chromadb is no longer an app dependency, so install it locally just for this,
   then run the script from `backend/` (a dry run first; it only reads Chroma):
   ```bash
   .venv/Scripts/python.exe -m pip install chromadb
   .venv/Scripts/python.exe scripts/migrate_chroma_to_pgvector.py --database-url "postgresql://neondb_owner:XXXX@ep-....neon.tech/neondb?sslmode=require"
   .venv/Scripts/python.exe scripts/migrate_chroma_to_pgvector.py --database-url "..." --apply
   ```
   It matches each vector to its chunk (by `chunks.chroma_id`, else by document
   and position), creates the `vector` extension and table if needed, skips
   chunks that already have a vector (safe to re-run), and reports vectors of
   deleted documents and chunks without a vector. Add `--embed-missing` to embed
   those chunks too. Chroma's vectors and fastembed's are the same model's (they
   match to within rounding), so old and new vectors search together.

   **Rather not install chromadb?** `--skip-chroma` doesn't read Chroma at all
   and embeds every chunk from its text instead (same vectors; a few minutes for
   a few thousand chunks):
   ```bash
   .venv/Scripts/python.exe scripts/migrate_chroma_to_pgvector.py --database-url "..." --skip-chroma --apply
   ```
3. Sign in later with the same account as locally; your documents come along
   with it.

### 1b. Local development after this

The backend now needs pgvector on whatever Postgres `DATABASE_URL` points to;
against a server without it, startup stops with an error saying so. A local
Windows Postgres usually doesn't have pgvector. Two options:

- **A Neon branch for development** (recommended): Neon project → **Branches** →
  **Create branch** (e.g. `dev`, from `main`), and put its connection string in
  `backend/.env`. It is a separate copy, so local experiments don't touch the
  deployed data.
- **Install pgvector** on your local server: <https://github.com/pgvector/pgvector#installation>.

---

## 2. Render (backend)

`render.yaml` at the repository root describes the service (a Render
"Blueprint"): a free Python web service built from `backend/`.

- Build: `pip install -r requirements.txt && python -m app.services.embedding_service`.
  The second command downloads the embedding model into `backend/.fastembed_cache`
  (`FASTEMBED_CACHE_PATH`), which ships with the build, so restarts don't download it.
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check: `/api/v1/health`
- Python 3.11.9 (`PYTHON_VERSION`)

Steps:

1. **Set the region first.** In `render.yaml`, `region: singapore` must match your
   Neon region (step 1). A service's region can't be changed later. Commit and
   push if you change it.
2. Sign up at <https://render.com> with GitHub. **New → Blueprint**, pick this
   repository. Render reads `render.yaml` and shows the `secondbrain-api` service.
3. It asks for the values marked `sync: false`:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string from step 1 |
   | `OPENROUTER_API_KEY` | your key from <https://openrouter.ai/keys> |
   | `APP_BASE_URL` | your Vercel URL, e.g. `https://secondbrain.vercel.app` (used in password reset links; if you don't know it yet, put a placeholder and fix it in step 4) |

   Already set by the Blueprint: `SESSION_COOKIE_SECURE=true` (Vercel serves
   HTTPS), `ALLOW_SIGNUP=true`, `EMBEDDING_THREADS=1`, `FASTEMBED_CACHE_PATH`,
   `PYTHON_VERSION`.
4. **Apply.** The first build takes a few minutes. Then open the service's URL
   plus `/api/v1/health`, e.g. `https://secondbrain-api.onrender.com/api/v1/health`
   → `{"status":"healthy",…}`. The URL is at the top of the service page (if the
   name was taken, Render adds a suffix - use exactly what it shows).
5. Optional settings, in the service's **Environment** tab (saving restarts it):

   | Name | Value |
   |---|---|
   | `BREVO_API_KEY` (+ `EMAIL_FROM`, `EMAIL_FROM_NAME`) | password reset emails through Brevo; without it, reset links are printed in the service's **Logs** |
   | `OPENROUTER_MODEL`, `OCR_MODEL` | see `backend/.env.example` |
   | `MERGED_MAX_CHARS`, `MERGED_MAX_DOC_CHARS`, `SUMMARY_PARALLEL_CALLS`, `NEW_CARDS_PER_DAY`, `PASSWORD_RESET_MINUTES` | defaults as in `backend/.env.example` |

Every push to `main` redeploys the backend (`autoDeploy: true`).

---

## 3. Vercel (frontend)

1. **Point the rewrite at Render.** In `frontend/vercel.json`, replace
   `https://YOUR-RENDER-SERVICE.onrender.com` with your service's URL from step 2
   (keep `/api/:path*` on the end). Commit and push.
   ```json
   { "source": "/api/:path*", "destination": "https://secondbrain-api.onrender.com/api/:path*" }
   ```
   The second rule sends every other path (e.g. `/library/12/summary` after a
   page refresh) to `index.html` for React Router; real files like
   `/assets/*.js` are served before rewrites apply.
2. Sign up at <https://vercel.com> with GitHub and **Add New… → Project**; import
   this repository.
3. Configure the project:
   - **Root Directory:** `frontend` (click **Edit** next to it - important)
   - **Framework Preset:** Vite (detected); build `npm run build`, output `dist`
   - No environment variables are needed.
4. **Deploy** and note the production URL, e.g. `https://secondbrain.vercel.app`.
   Every push to `main` redeploys it.

## 4. Finish

1. On Render, set `APP_BASE_URL` to the Vercel URL (no trailing slash).
2. Open the Vercel URL, sign up (or log in with an account you brought over),
   upload a small PDF, and run a search. Reload the page and check you're still
   logged in.
3. If the app is only for you, set `ALLOW_SIGNUP=false` on Render.

---

## Things to know

- **Sleep and cold starts.** A free Render service sleeps after about 15 minutes
  without traffic; the next request wakes it, which takes up to a minute or so.
  The first upload or search after that also loads the embedding model (a few
  seconds). Pages show errors while it wakes; refresh after a moment.
- **Free hours.** Render's free plan has a monthly allowance of instance hours
  per workspace (enough for one always-on service at the time of writing; check
  Render's pricing page). A sleeping service uses none.
- **Long AI requests.** Every API call goes through Vercel's proxy, which only
  waits a limited time for the backend. A very long summary of a big document or
  merged set can be cut off with a Vercel 504 even though the backend finishes
  it; the summary is saved, so opening the page again shows it.
- **Upload size.** Large uploads also go through the proxy. If a big PDF fails
  on Vercel but works locally, try a smaller file.
- **Logs.** Backend: Render service → **Logs**. Frontend: Vercel project →
  **Logs**. Database: Neon console → **Monitoring**.
- **Neon's free plan** suspends the database after a few minutes without
  queries; the first request after that waits a moment while it wakes. The app
  checks pooled connections before use, so this doesn't cause errors.
- **Secrets** live only in Render's environment settings; never commit
  `backend/.env`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Render log: `DATABASE_URL is not set` | the variable is missing on Render (Environment tab) |
| Render log: `Couldn't enable the pgvector extension` | `DATABASE_URL` points at a Postgres without pgvector (e.g. a local server); use the Neon string |
| Render log: connection timed out / SSL error to `*.neon.tech` | wrong connection string, or `?sslmode=require` was dropped |
| Render build fails in `pip install` | check the Python version is 3.11.9 (`PYTHON_VERSION`) |
| Render event: "Ran out of memory (used over 512MB)" | check the log for what was running: big uploads (many-page PDFs, scanned pages sent to OCR) use the most memory. Keep `EMBEDDING_THREADS=1`; try smaller files |
| Every page says you're logged out / login loops back | `SESSION_COOKIE_SECURE` must be `true`, and the site must be opened through the Vercel URL, not the `onrender.com` one |
| `/api/...` on Vercel returns 404 or Vercel's error page | `frontend/vercel.json` still has the placeholder, or the Render URL is wrong |
| Refreshing `/library` on Vercel gives 404 | the Vercel project's root directory isn't `frontend`, so `vercel.json` isn't used |
| Search finds nothing for documents you moved from local | the vectors weren't copied: run `scripts/migrate_chroma_to_pgvector.py` against Neon (step 1a) |
| Password reset link points to localhost | set `APP_BASE_URL` on Render |
