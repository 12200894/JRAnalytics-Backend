# Setup Guide

Things that aren't obvious from just cloning this repo. Follow in order.

## 1. Requirements

- Python 3.11+
- PostgreSQL 16 (must be actually installed and running as a service — not bundled with this repo)

## 2. Database

```bash
# In psql, or any Postgres GUI:
CREATE DATABASE jranalytics;
```

If PostgreSQL was just installed, you may need to set a password for the `postgres` user
first (it doesn't have one by default on some installers):

```bash
psql -U postgres -c "ALTER USER postgres WITH PASSWORD 'your-password-here';"
```

## 3. Python environment

```bash
python -m venv venv
./venv/Scripts/pip install -r requirements.txt      # Windows
./venv/bin/pip install -r requirements.txt           # macOS/Linux
```

## 4. Environment variables

```bash
cp .env.example .env
```

Then edit `.env`:
- `DB_USER` / `DB_PASSWORD` — must match whatever you set up in step 2
- `DJANGO_SECRET_KEY` — any random string for local dev is fine
- `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` — only needed if you want password-reset
  emails to actually send. See "Email setup" below. Leave blank to skip — everything
  else works fine without it, you'll just get an error if someone taps "Forgot Password."

## 5. Migrate and run

```bash
./venv/Scripts/python.exe manage.py migrate
./venv/Scripts/python.exe manage.py createsuperuser   # optional, for /admin/
./venv/Scripts/python.exe manage.py runserver 8000
```

Backend is now at `http://127.0.0.1:8000`.

## Email setup (for password reset)

The password-reset feature sends real email via Gmail SMTP. You need a Gmail account
to send *from* (not related to any user's own email — this is just the app's sender
identity):

1. On that Gmail account: **myaccount.google.com/security** → turn on **2-Step Verification**
2. **myaccount.google.com/apppasswords** → create one, name it anything
3. Copy the 16-character code Google shows you (you only see it once)
4. In `.env`:
   ```
   EMAIL_HOST_USER=your-address@gmail.com
   EMAIL_HOST_PASSWORD=the16characteapppassword
   ```

## Windows-specific gotchas

- If `manage.py` commands hang or fail oddly in Git Bash, use a regular **PowerShell**
  or **Command Prompt** window instead.
- This project was built/tested with Python 3.14 via a local venv; other 3.11+ versions
  should work fine too.

## The LLM service (optional but needed for AI summaries)

This backend calls a separate service (see the `JRAnalytics-LLM` repo) for the
`/summaries/generate/` endpoint. Without it running, that one endpoint returns a 503 —
everything else in this backend works fine regardless.
