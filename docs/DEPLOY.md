# Deploying SecondBrain for free

| Part | Host | What runs there |
|---|---|---|
| Database | [Neon](https://neon.tech) (free Postgres) | every table, including each chunk's text |
| Backend | [Hugging Face Spaces](https://huggingface.co/spaces) (Docker, free CPU) | FastAPI on port 7860, Chroma, the embedding model |
| Frontend | [Vercel](https://vercel.com) (Hobby) | the built React app |

```
browser ──► https://<app>.vercel.app/            static files (Vercel)
        └─► https://<app>.vercel.app/api/...  ──rewrite──► https://<user>-<space>.hf.space/api/...
```

The browser only ever talks to the Vercel domain. `frontend/vercel.json` forwards
`/api/*` to the Space, so the `sb_session` login cookie is set by, and sent back to,
the same origin as the page. No CORS setup is needed, and the frontend code
(`const API_BASE_URL = '/api'`) is unchanged from local development.

**About the vector store.** A free Space has no persistent disk: Chroma's index
(`vector_db/`) and the original upload files (`uploads/`) are gone after every
restart or rebuild. Postgres has every chunk, so on startup the backend checks
whether the Chroma collection is empty and, if so, re-embeds every chunk with the
same id and metadata an upload gives it (`user_id`, `document_id`, `filename`,
`source_type`, `chunk_index`, `source_url`, YouTube `start_seconds`, PDF/image
`page_start`/`page_end`); see `app/database/chroma_rebuild.py`. The log then shows
`Vector store was empty: rebuilt N chunks from Postgres in X s`. Summaries,
flashcards and quizzes are in Postgres and don't depend on the original files;
only `scripts/reindex_pdf_pages.py` needs them, and it is a one-off local tool.

Do the steps in order: Neon → Hugging Face → Vercel → back to Hugging Face for
`APP_BASE_URL`.

---

## 1. Neon (database)

1. Sign up at <https://console.neon.tech> and **Create project**.
   - Postgres version: the default.
   - Region: **AWS US East (N. Virginia)** or whichever is closest to where your
     Space runs; every API request makes several database round trips, so a
     nearby region matters more than anything else here.
2. On the project dashboard, click **Connect**. Pick the `neondb` database and
   the default role, and **turn off "Connection pooling"** (use the direct
   connection; the app keeps its own small pool). Copy the connection string. It
   looks like:
   ```
   postgresql://neondb_owner:XXXXXXXX@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
3. That string, unchanged, is your `DATABASE_URL`. (Keep `?sslmode=require`;
   `postgresql+psycopg2://…` also works.) Treat it as a password.
4. Nothing else to do: the backend creates and migrates its tables on startup
   (`init_db()`).

**Optional: bring your local data along.** From a machine with the Postgres
client tools (use a `pg_dump` at least as new as the local server):

```bash
pg_dump --no-owner --no-acl -Fc "postgresql://postgres:PASSWORD@localhost:5432/secondbrain" -f secondbrain.dump
pg_restore --no-owner --no-acl -d "postgresql://neondb_owner:XXXX@ep-....neon.tech/neondb?sslmode=require" secondbrain.dump
```

Do this **before** the backend's first start against Neon (or into an empty
database), so `pg_restore` doesn't collide with tables `init_db()` already made.
You don't need to copy `vector_db/`: the first start on the Space rebuilds it.
(`*.dump` files are not in `.gitignore` - don't commit them.)

Neon's free plan suspends the database after a few minutes without queries; the
first request after that waits a moment while it wakes. The app checks pooled
connections before use (`pool_pre_ping`), so a suspended database doesn't cause
errors. Check Neon's pricing page for the current free storage limit.

---

## 2. Hugging Face Spaces (backend)

### 2.1 Create the Space

1. Sign up at <https://huggingface.co> and go to **New Space**
   (<https://huggingface.co/new-space>).
2. - **Space name:** e.g. `secondbrain-api`
   - **SDK:** **Docker** → **Blank** template
   - **Hardware:** **CPU basic (free)**
   - **Visibility:** **Public**. Vercel's proxy can't log in to a private Space.
     Only the code is public; secrets stay private (next step), and every API
     endpoint except health and auth still needs a login.
3. The Space's API address is `https://<username>-<space-name>.hf.space`
   (lower case, with anything other than letters and digits turned into `-`),
   e.g. `https://jane-secondbrain-api.hf.space`. You can also find it under the
   Space's **⋮ → Embed this Space → Direct URL**. Note it down.

### 2.2 Settings → Variables and secrets

Add these in the Space's **Settings → Variables and secrets** *before* the first
build. Use **New secret** for anything sensitive and **New variable** for the rest.

| Name | Type | Value |
|---|---|---|
| `DATABASE_URL` | secret | the Neon connection string from step 1 |
| `OPENROUTER_API_KEY` | secret | your key from <https://openrouter.ai/keys> |
| `SESSION_COOKIE_SECURE` | variable | `true` (Vercel serves HTTPS) |
| `APP_BASE_URL` | variable | your Vercel URL, e.g. `https://secondbrain.vercel.app` (set it after step 3 if you don't know it yet; used in password reset links) |
| `ALLOW_SIGNUP` | variable | `true` until your account exists, then `false` if the app is just for you |
| `BREVO_API_KEY` | secret | optional, for password reset emails (otherwise the link is printed in the Space's logs) |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | variable | optional, with Brevo: a sender verified in Brevo |
| `OPENROUTER_MODEL`, `OCR_MODEL` | variable | optional, see `backend/.env.example` |
| `MERGED_MAX_CHARS`, `MERGED_MAX_DOC_CHARS`, `SUMMARY_PARALLEL_CALLS`, `NEW_CARDS_PER_DAY`, `PASSWORD_RESET_MINUTES` | variable | optional, defaults as in `backend/.env.example` |

Already set in the image, no need to add: `PORT=7860`,
`CHROMA_DIR=/home/user/app/vector_db`. Changing a variable or secret restarts
the Space.

### 2.3 Push the backend to the Space

A Space is a git repository whose root must hold the `Dockerfile` and a
`README.md` with the Space settings; in this repo those are in `backend/`
(`backend/README.md` starts with that settings block: `sdk: docker`,
`app_port: 7860`, and a 1 hour `startup_duration_timeout` so a first-time
rebuild of a large library isn't cut off). So push only the `backend/` folder:

1. Create a Hugging Face access token with **write** permission:
   <https://huggingface.co/settings/tokens>.
2. From the repository root:
   ```bash
   git remote add space https://huggingface.co/spaces/<username>/<space-name>
   git subtree split --prefix backend -b space-deploy
   git push space space-deploy:main --force
   ```
   When git asks for credentials, the username is your Hugging Face username and
   the password is the token. (`--force` replaces the starter files the Space was
   created with; your GitHub history isn't touched.)
3. The Space's **App** tab shows **Building**; the **Logs** button shows the
   Docker build. The first build takes several minutes (torch, the embedding
   model). When it is **Running**, the container log should end with lines like:
   ```
   Model openai/gpt-4o-mini: context 128000 tokens, max output 16384 tokens
   Vector store was empty: rebuilt 1234 chunks from Postgres in 41.7 s   (only if there are chunks)
   Uvicorn running on http://0.0.0.0:7860
   ```
4. Check it: open `https://<username>-<space-name>.hf.space/api/v1/health` →
   `{"status":"healthy",…}`.

To update the backend later, commit to `main` as usual, then run the same two
commands again:

```bash
git subtree split --prefix backend -b space-deploy
git push space space-deploy:main --force
```

(`git subtree split` reuses its earlier work, so this stays quick.)

---

## 3. Vercel (frontend)

1. **Point the rewrite at your Space.** In `frontend/vercel.json`, replace
   `https://YOUR-HF-USERNAME-secondbrain-api.hf.space` with your Space's URL
   from 2.1 (keep `/api/:path*` on the end). Commit and push to GitHub.
   ```json
   { "source": "/api/:path*", "destination": "https://jane-secondbrain-api.hf.space/api/:path*" }
   ```
   The second rule sends every other path (e.g. `/library/12/summary` after a
   page refresh) to `index.html`, so React Router can handle it; real files
   like `/assets/*.js` are served before rewrites apply.
2. Sign up at <https://vercel.com> with GitHub and **Add New… → Project**;
   import this repository.
3. Configure the project:
   - **Root Directory:** `frontend` (important - click **Edit** next to it)
   - **Framework Preset:** Vite (detected)
   - Build command `npm run build`, output directory `dist` (the defaults)
   - No environment variables are needed.
4. **Deploy.** Note the production URL, e.g. `https://secondbrain.vercel.app`.
5. Every push to `main` now redeploys the frontend automatically.

## 4. Finish

1. In the Space's **Settings → Variables and secrets**, set `APP_BASE_URL` to the
   Vercel URL (no trailing slash). The Space restarts.
2. Open the Vercel URL, sign up (or log in with an account you brought over from
   your local database), upload a small PDF, and run a search. Reload the page
   and check you are still logged in.
3. If the app is only for you, set `ALLOW_SIGNUP=false` on the Space.
4. Optional: test the rebuild. **Settings → Factory rebuild** on the Space,
   then confirm search still finds your documents and the log shows the
   `rebuilt N chunks` line.

---

## Things to know

- **Sleep and cold starts.** A free Space sleeps after a period without traffic
  (48 hours at the time of writing). The next visit starts the container again,
  which wipes Chroma, so that first request waits for startup *and* the rebuild
  (roughly a minute per few thousand chunks on the free CPU). Pages show errors
  until it is up; refresh after a minute.
- **Long AI requests.** Every API call goes through Vercel's proxy, which only
  waits a limited time for the backend. A very long summary of a big document or
  merged set can be cut off with a Vercel 504 even though the Space finishes it;
  the summary is saved, so opening the page again shows it.
- **Upload size.** Large uploads also go through the proxy. If a big PDF fails
  on Vercel but works locally, try a smaller file.
- **Logs.** Backend: the Space's **Logs** button (container logs). Frontend:
  Vercel project → **Logs**. Password reset links appear in the Space log when
  `BREVO_API_KEY` isn't set.
- **Secrets.** Never commit `backend/.env`; the Docker image doesn't include it
  (`backend/.dockerignore`), and every setting comes from the Space's variables
  and secrets.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Space log: `DATABASE_URL is not set` | the secret is missing or misspelled; add it and the Space restarts |
| Space log: connection timed out / SSL error to `*.neon.tech` | wrong connection string, or `sslmode=require` was dropped. Spaces allow outbound Postgres connections on port 5432. |
| Space stuck on **Building** then **Runtime error** | open **Logs**; a failed `pip install` shows in the build log, a Python error in the container log |
| Every page says you're logged out / login loops back to the login page | `SESSION_COOKIE_SECURE` must be `true`; the site must be opened through the Vercel URL, not the `hf.space` one |
| `/api/...` on Vercel returns 404 or Vercel's error page | `frontend/vercel.json` still has the placeholder, or the Space URL is wrong / the Space is private or asleep |
| Refreshing `/library` on Vercel gives 404 | the Vercel project's root directory isn't `frontend`, so `vercel.json` isn't used |
| Search finds nothing after a restart | check the log for the `rebuilt N chunks` line; if the collection was not empty (e.g. a crash mid-rebuild), **Factory rebuild** the Space |
| Password reset link points to localhost | set `APP_BASE_URL` on the Space |
