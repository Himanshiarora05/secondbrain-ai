# SecondBrain

A study notes summarizer. Add your study material, and SecondBrain turns it into concise revision notes, flashcards, and a searchable knowledge base you can ask questions about.

## What it does

- **Accounts**: sign up with an email and password. Your documents, summaries, flashcards, merged sets and search results are private to your account; nobody else can see or open them, even with a direct link. Forgot your password? **Forgot password?** on the login page emails you a link to set a new one (it works once, expires after 30 minutes, and logs you out everywhere). See [Password reset emails](#password-reset-emails).
- **Add sources**: PDF, PowerPoint (`.pptx`), Word (`.docx`), YouTube videos (with captions), and website links. You can pick or drop several files at once. Each becomes its own document, and afterwards the app offers to make a merged set from them straight away.
- **Summaries**: exam-revision notes for each source.
  - YouTube summaries link every point to its moment in the video (`[02:05]`).
  - PDF summaries cite the page of every point (`(p. 12)`, `(pp. 12–13)`), PowerPoint summaries the slide (`(Slide 4)`).
  - Website summaries end with a link back to the original page.
- **Flashcards**: question-and-answer cards generated from any source, spread across the whole source. Each card shows where it came from: the video moment, the web page, the PDF page or the slides (Word cards don't show a location).
- **Merged sets**: select 2–8 sources of any type in the Library (**Select**, tick them, **Create merged set**) and get one summary and one flashcard deck from all of them together.
  - Every point still says which source and where: `(1: p. 12)`, `(2: Slide 4)`, `[3: 02:05]`, with a numbered list of the sources at the top. Cards say, for example, "Graph_PPT.pdf · p. 12".
  - A set has its own summary and deck, so each document's own summary and flashcards stay as they are. Picking the same documents again opens the existing set instead of making a copy.
  - Limits: 8 documents and 80,000 characters of text per set. If you delete a document, the set says its summary and cards are out of date until you regenerate them.
- **Ask questions**: search across everything you've saved and get an AI answer, with links to the sources it used (the exact video moment for YouTube, the page for websites) and the page for PDFs.
- **No duplicate links**: adding a web page or YouTube video that's already in your library is refused, with an "Open it" link to the saved copy. Different forms of the same link count as the same (`http`/`https`, `www.`, `#section` or tracking parameters for pages; `youtu.be`, `/shorts/` or `&t=` for videos). To re-import, delete the saved copy first.
- **Clear AI errors**: if the AI service can't respond (out of credits, invalid API key, rate limit, the daily free-model limit, timeout, outage), the page says so in plain words. The technical details go to the backend log. Momentary failures, such as an overloaded provider, are retried automatically.

Old `.ppt` and `.doc` files aren't supported; save them as `.pptx` / `.docx` first. Scanned PDFs (pages that are only images, with no selectable text) can't be read yet; run them through OCR first. Website import only reads public pages (no logins, paywalls, or JavaScript-only apps) up to 5 MB, and blocks local and private network addresses.

## How it's built

| Part | Stack |
|---|---|
| `backend/` | FastAPI, PostgreSQL (documents, chunks, summaries, flashcards), Chroma (vector search), `all-MiniLM-L6-v2` embeddings, OpenRouter for the AI model |
| `frontend/` | React 19, Vite, TypeScript, Tailwind CSS v4 |

The frontend's dev server forwards `/api` requests to the backend on port 8000, so run both.

## Prerequisites

- **Python 3.11**
- **Node.js 20.19+ or 22.12+** (required by Vite 8)
- **PostgreSQL** running locally or somewhere you can reach
- **An OpenRouter API key**: get one at [openrouter.ai](https://openrouter.ai). It's used for summaries, flashcards, and answers, and the backend won't start without it.

The Python dependencies are large (PyTorch and other ML libraries), so the first install can take a while and several GB of disk space. The first upload or search also downloads the embedding model (about 90 MB) from Hugging Face.

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Himanshiarora05/secondbrain-ai.git
cd secondbrain-ai
```

### 2. Create the database

Create an empty PostgreSQL database. The app creates its tables itself on first start.

```bash
createdb secondbrain
```

(Or run `CREATE DATABASE secondbrain;` in `psql` or pgAdmin.)

### 3. Configure `backend/.env`

Copy the example file:

```bash
cd backend
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env
```

Then edit `backend/.env`:

| Variable | What to set |
|---|---|
| `DATABASE_URL` | Your Postgres connection string, e.g. `postgresql+psycopg2://postgres:<your password>@localhost:5432/secondbrain`. **Required**: the backend won't start without it. |
| `OPENROUTER_API_KEY` | Your OpenRouter key. **Required**: the backend won't start without it. |
| `CHROMA_DIR` | Where the vector index is stored. The default `vector_db` is fine. |
| `SQL_ECHO` | `true` logs every SQL statement (noisy; for debugging). Default `false`. |
| `ALLOW_SIGNUP` | `false` closes sign-up once your account exists; existing accounts can still log in. Default `true`. |
| `SESSION_COOKIE_SECURE` | `true` sends the login cookie over HTTPS only. Set it when the app is served over HTTPS; leave it off for `http://localhost`. Default `false`. |
| `BREVO_API_KEY`, `EMAIL_FROM` | Your Brevo API key and verified sender address, for password reset emails. Optional: without them, reset links are written to the backend log instead. See [Password reset emails](#password-reset-emails). |
| `EMAIL_FROM_NAME` | The sender name on emails. Default `SecondBrain`. |
| `APP_BASE_URL` | Where the frontend runs, for the link in reset emails. Default `http://localhost:5173`. |
| `PASSWORD_RESET_MINUTES` | How long a reset link works. Default `30`. |

`.env` is in `.gitignore`. Never commit it.

### 4. Install the backend

From `backend/`:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate          # macOS / Linux
.venv\Scripts\Activate.ps1         # Windows PowerShell
```

Then install:

```bash
pip install -r requirements.txt
```

### 5. Install the frontend

From `frontend/`:

```bash
npm install
```

## Running

Use two terminals.

**Backend** (from `backend/`, with the virtual environment active):

```bash
python -m uvicorn main:app --reload
```

Run it from `backend/`: uploaded files (`uploads/`) and the vector index (`vector_db/`) are stored relative to the current folder. The API runs on http://127.0.0.1:8000, with interactive API docs at http://127.0.0.1:8000/docs.

**Frontend** (from `frontend/`):

```bash
npm run dev
```

Open the URL Vite prints (usually http://localhost:5173) and create your account on the sign-up page.

## Password reset emails

"Forgot password?" sends its link through [Brevo](https://www.brevo.com). The free plan sends 300 emails a day and doesn't need a domain of your own.

1. Sign up at brevo.com.
2. **Senders, Domains & Dedicated IPs → Senders → Add a sender**: the address emails should come from (a Gmail address works). Confirm it with the 6-digit code Brevo emails to it.
3. **SMTP & API → API Keys → Generate a new API key**, and copy it.
4. In `backend/.env`, set `BREVO_API_KEY` to the key and `EMAIL_FROM` to the verified sender, then restart the backend (it reads `.env` only at start-up).

Until then, the backend writes each reset email, link included, to its log instead of sending it, so you can still reset a password locally by copying the link from the backend terminal. Emails sent from a Gmail address through Brevo can land in spam; tell users to check there.

## Upgrading from before accounts

Documents added before accounts existed have no owner, so after upgrading your library looks empty; nothing is lost. Sign up in the app, then give them to your account. From `backend/`:

```bash
python scripts/assign_documents_to_user.py --email you@example.com           # preview: lists what would change
python scripts/assign_documents_to_user.py --email you@example.com --apply   # assign them
```

This assigns every document and merged set that has no owner yet (with their summaries, flashcards and search entries) to that account. Documents that already belong to someone are never changed, so it's safe to run again.

## Page numbers for older PDFs

PDFs uploaded before page tracking don't cite pages yet. Their original files are kept in `backend/uploads/`, so they can be re-indexed without uploading again. From `backend/`:

```bash
python scripts/reindex_pdf_pages.py           # preview: lists what would change, changes nothing
python scripts/reindex_pdf_pages.py --apply   # re-index
```

This rebuilds each PDF's search chunks with page numbers. The document, its summary and its flashcards are kept; regenerate the summary or flashcards afterwards to get page citations.

## Development

Frontend checks, from `frontend/`:

```bash
npm run build    # type check + production build
npm run lint     # oxlint
```

Backend tests are plain scripts in `backend/tests/`, run one at a time from `backend/`:

```bash
python tests/test_website_ingestion.py
```

Only these are safe to run anywhere: they're fully offline (network, database, and AI calls are mocked):

- `test_youtube_summary_citations.py`
- `test_website_ingestion.py`
- `test_office_formats.py`
- `test_flashcard_citations.py`
- `test_concurrent_generation.py`
- `test_youtube_duplicates.py`
- `test_ai_error_messages.py`
- `test_pdf_page_citations.py`

The other scripts run against your **real** database, vector index, and OpenRouter account, and some delete data. Read a script before running it.

`CLAUDE.md` has more detail on the architecture and conventions.
