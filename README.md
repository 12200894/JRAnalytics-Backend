# JR Analytics Backend

Django REST API for the JR Analytics health notes app. Handles users, auth, notes and AI
summaries. Calls the LLM service for summarisation.

## Setup

Needs PostgreSQL 16 and Python 3.11.

```bash
brew install postgresql@16
brew services start postgresql@16
createdb jranalytics
```

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
./venv/bin/python manage.py migrate
./venv/bin/python manage.py createsuperuser
```

## Running it

```bash
./venv/bin/python manage.py runserver
```

Admin at http://127.0.0.1:8000/admin/

Summary generation needs the LLM service running on port 8001. Without it the API still
works, `/summaries/generate/` just returns 503.

## Endpoints

```
POST   /api/v1/auth/register/       create account, returns JWT
POST   /api/v1/auth/login/          get JWT
POST   /api/v1/auth/refresh/        refresh the access token
GET    /api/v1/auth/me/             profile
GET    /api/v1/notes/               list notes (?type= and ?q= filters)
POST   /api/v1/notes/               create a note
GET    /api/v1/notes/{id}/          one note (also PUT, PATCH, DELETE)
GET    /api/v1/summaries/           past summaries
POST   /api/v1/summaries/generate/  generate one, calls the LLM service
GET    /api/v1/llm/status/          is the LLM service up
```

Everything except register/login needs `Authorization: Bearer <token>`.

## Notes

A note has a type: `free`, `symptom`, `medication` or `appointment`. Template values go in
the `fields` JSON object and are validated against the type:

```json
{
  "note_type": "symptom",
  "title": "Headache",
  "body": "Behind both eyes since 3pm.",
  "fields": {"severity": "6/10", "duration": "3 hours", "triggers": "Screen time"},
  "tags": ["headache"]
}
```

- symptom: severity, duration, triggers
- medication: medication, dose, frequency
- appointment: clinician, date, outcome
- free: no fields

## Tables

`accounts_user`, `notes_healthnote`, `notes_attachment`, `notes_aisummary`,
`notes_aisummary_source_notes`.

```bash
psql -d jranalytics -c "\dt"
```

## Demo script

```bash
./demo.sh
```

Runs through register, login, create notes, generate a summary and show the database rows.
Pauses between steps. Use `--fast` to skip the pauses.

## Config

Settings come from `.env`. See `.env.example`. `.env` is gitignored.

`DJANGO_SECRET_KEY` has an insecure default for development. The app refuses to start with
`DEBUG=False` unless you set a real one.

## Not done yet

Celery for background inference (summaries currently block for about 20 seconds), S3
attachment uploads, pgvector semantic search, admin endpoints, email.
