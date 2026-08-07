# JR Analytics — Backend

Django REST API for the JR Analytics health notes application. Owns users, authentication,
health notes and AI summaries. Calls the LLM service over HTTP for summarisation.

```
React Native  →  Django + DRF :8000  →  FastAPI LLM service :8001
                       ↓                          ↑
                  PostgreSQL 16             model_v11.pt (209 MB)
```

**Why the LLM is a separate service.** If Django imported the model directly, every worker
process would hold 209 MB in memory, beam search would block that worker for seconds, and
PyTorch would sit in the web application's dependency tree. Keeping it behind HTTP means the
API stays fast, the AI tier scales independently, and a new model version ships without
redeploying the backend.

---

## Starting everything

Three processes. Open three terminal tabs.

**1 · PostgreSQL** — runs as a background service, starts at login:

```bash
brew services start postgresql@16
```

**2 · LLM service** (port 8001) — loads the model once, takes about 15 seconds:

```bash
cd "/Users/saphalraya/Desktop/JR Analytics LLM" && python3 -m uvicorn service:app --port 8001
```

**3 · Django** (port 8000):

```bash
cd "/Users/saphalraya/Desktop/JR Analytics Backend" && ./venv/bin/python manage.py runserver
```

Check all three are healthy:

```bash
pg_isready && curl -s localhost:8001/health && curl -s localhost:8000/admin/ -o /dev/null -w "%{http_code}\n"
```

---

## What exists

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/auth/register/` | Create account, returns JWT pair |
| POST | `/api/v1/auth/login/` | Obtain JWT pair |
| POST | `/api/v1/auth/refresh/` | Exchange refresh token for a new access token |
| GET PATCH | `/api/v1/auth/me/` | Read / update the signed-in profile |
| GET POST | `/api/v1/notes/` | List and create health notes |
| GET PUT PATCH DELETE | `/api/v1/notes/{id}/` | Retrieve, update, delete one note |
| GET | `/api/v1/summaries/` | Past AI summaries |
| POST | `/api/v1/summaries/generate/` | Generate a summary via the LLM service |
| GET | `/api/v1/llm/status/` | Is the AI tier reachable? |
| — | `/admin/` | Django admin — full CRUD over every table |

Notes support `?type=symptom` and `?q=keyword`.

### Database tables

| Table | Holds |
|---|---|
| `accounts_user` | Email-keyed users, hashed passwords, preferences, privacy consent timestamp |
| `notes_healthnote` | Notes with `note_type`, `title`, `body`, JSONB `fields`, JSONB `tags` |
| `notes_attachment` | Photos and PDFs linked to a note |
| `notes_aisummary` | Generated summaries with status and model version |
| `notes_aisummary_source_notes` | Which notes produced which summary — the provenance trail |
| `token_blacklist_*` | Revoked refresh tokens, so a logged-out token cannot be replayed |

Inspect any of them:

```bash
psql -d jranalytics -c "\dt"
psql -d jranalytics -c "SELECT id, note_type, title FROM notes_healthnote;"
```

---

## Design decisions worth being able to explain

**Custom user model, keyed on email.** Django's default requires a username. Health apps
identify people by email, and swapping the user model after migrations exist is painful, so
it was done before the first migration.

**JSONB for template fields.** A note is free-form, symptom, medication or appointment. One
`fields` column serves all four, and the serializer validates against the template for that
type. Adding a fifth template later needs a serializer change, not a migration.

**Queryset-level user scoping.** `HealthNoteViewSet.get_queryset()` filters by
`self.request.user`. Because filtering happens in the queryset rather than in each view,
there is no code path that can return another user's record — including any view added later.

**Short-lived JWTs with rotation.** 15-minute access tokens, 7-day refresh tokens, rotated on
use and blacklisted afterwards. A leaked access token is useful for minutes, and logout
genuinely revokes.

**Consent timestamped at registration.** `privacy_consent_at` records when the user agreed,
which is what Australian Privacy Principle 3 requires. Registration rejects without it.

**HTTP client with typed failures.** `notes/llm_client.py` distinguishes connection refused,
timeout and HTTP error, and returns 503 with an actionable message rather than a 500 stack
trace. The API stays up when the AI tier is down.

---

## Verified working

Full sequence, from an empty database:

```bash
# register
curl -X POST localhost:8000/api/v1/auth/register/ -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","full_name":"Your Name","password":"Health123",
       "password_confirm":"Health123","privacy_consent":true}'

# login — capture the access token
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login/ -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"Health123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access'])")

# create a note
curl -X POST localhost:8000/api/v1/notes/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"note_type":"symptom","title":"Headache","body":"Behind both eyes since 3pm.",
       "fields":{"severity":"6/10","duration":"3 hours","triggers":"Screen time"},
       "tags":["headache"]}'

# generate a summary — Django calls the LLM service
curl -X POST localhost:8000/api/v1/summaries/generate/ -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"period":"week"}'
```

Confirmed behaviours: registration rejects passwords under 8 characters, passwords with no
digit, mismatched confirmations, duplicate emails and missing consent. Notes reject template
fields belonging to a different note type. Unauthenticated requests to `/api/v1/notes/`
return 401. Summary generation returns 503 with a clear message when the LLM service is down.

---

## Two things this run exposed

**Vocabulary drift is real.** The first summary generated from live user notes came back
containing `<unk>` tokens. The v11 vocabulary was fitted on synthetic clinical logs, and real
free-text notes contain words it has never seen. This is the risk named in the implementation
plan, now observed rather than predicted.

**The faithfulness problem shows up through the API too.** The generated summary reported "no
home-monitoring log entries were recorded" and a "14-day monitoring window" for a 7-day
request containing three notes. The stored `daily_lines` — produced by the deterministic
parser — were correct. Nothing about wrapping the model in HTTP changes this; it is a model
issue, documented in the LLM repository.

Both are arguments for `render_note_log()` in `notes/views.py` becoming more careful about
the format it produces, and for the numeric-substitution fix described in the LLM README.

---

## Not built yet

Celery and Redis for asynchronous inference — currently `generate/` calls the LLM
synchronously and the client waits about 19 seconds on CPU. Attachment upload to S3 with
pre-signed URLs. pgvector and semantic search. Administrator endpoints. Email notifications.
These are Sprints 3 to 5 in the implementation plan.
