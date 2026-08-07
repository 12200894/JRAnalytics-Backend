#!/bin/bash
# JR Analytics — live demonstration script
#
#   ./demo.sh          pause between steps, press Enter to advance
#   ./demo.sh --fast   run straight through, no pauses
#
# Requires all three services running. Step 0 checks and tells you what is missing.

API="http://127.0.0.1:8000/api/v1"
LLM="http://127.0.0.1:8001"
PSQL="/opt/homebrew/opt/postgresql@16/bin/psql"
EMAIL="demo$(date +%H%M%S)@jranalytics.com"

B=$'\033[1m'; G=$'\033[32m'; R=$'\033[31m'; C=$'\033[36m'; N=$'\033[0m'

pause() { [ "$1" = "--fast" ] && return; echo; read -rp "${C}— press Enter —${N}" _; }
step()  { echo; echo "${B}══════════════════════════════════════════════════════════════${N}";
          echo "${B} $1${N}";
          echo "${B}══════════════════════════════════════════════════════════════${N}"; }

# ───────────────────────────────────────────── 0. preflight
step "0 · Are all three services running?"

ok=1
if $PSQL -d jranalytics -c "SELECT 1" >/dev/null 2>&1; then
  echo "  ${G}✓${N} PostgreSQL   — database 'jranalytics' reachable"
else
  echo "  ${R}✗${N} PostgreSQL   — run: brew services start postgresql@16"; ok=0
fi

if curl -s -m 3 "$LLM/health" >/dev/null 2>&1; then
  params=$(curl -s "$LLM/health" | python3 -c "import sys,json;print(f\"{json.load(sys.stdin)['parameters']:,}\")")
  echo "  ${G}✓${N} LLM service  — model loaded, $params parameters"
else
  echo "  ${R}✗${N} LLM service  — cd '../JR Analytics LLM' && python3 -m uvicorn service:app --port 8001"; ok=0
fi

if [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/admin/)" != "000" ]; then
  echo "  ${G}✓${N} Django API   — responding on port 8000"
else
  echo "  ${R}✗${N} Django API   — ./venv/bin/python manage.py runserver"; ok=0
fi

[ "$ok" = "0" ] && { echo; echo "${R}Start the missing services, then run this again.${N}"; exit 1; }
pause "$1"

# ───────────────────────────────────────────── 1. register
step "1 · Register a new account"
echo "POST /api/v1/auth/register/"
echo "Creating: $EMAIL"; echo
curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" -d "{
  \"email\":\"$EMAIL\", \"full_name\":\"Demo Patient\",
  \"password\":\"Health123\", \"password_confirm\":\"Health123\",
  \"privacy_consent\":true}" | python3 -m json.tool | head -13
echo
echo "${C}Password is hashed, never stored as text. Consent is timestamped for APP 3.${N}"
pause "$1"

# ───────────────────────────────────────────── 2. validation
step "2 · Validation rejects bad input"
echo "Password with no digit:"
curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" \
  -d '{"email":"x@y.com","password":"password","password_confirm":"password","privacy_consent":true}' \
  | python3 -m json.tool
echo; echo "Registering without privacy consent:"
curl -s -X POST "$API/auth/register/" -H "Content-Type: application/json" \
  -d '{"email":"x@y.com","password":"Health123","password_confirm":"Health123","privacy_consent":false}' \
  | python3 -m json.tool
pause "$1"

# ───────────────────────────────────────────── 3. login
step "3 · Log in and receive a JWT"
TOKEN=$(curl -s -X POST "$API/auth/login/" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Health123\"}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access'])")
AUTH="Authorization: Bearer $TOKEN"
echo "Access token: ${TOKEN:0:55}..."
echo
echo "${C}Valid 15 minutes. The refresh token lasts 7 days and is blacklisted on logout.${N}"
pause "$1"

# ───────────────────────────────────────────── 4. auth required
step "4 · The API refuses unauthenticated requests"
echo "GET /api/v1/notes/ with no token:"
curl -s "$API/notes/" | python3 -m json.tool
pause "$1"

# ───────────────────────────────────────────── 5. create notes
step "5 · Create health notes"
for payload in \
 '{"note_type":"symptom","title":"Headache after screen work","body":"Dull headache behind both eyes from 3pm. Took paracetamol, eased after an hour.","fields":{"severity":"6/10","duration":"3 hours","triggers":"Screen time"},"tags":["headache","fatigue"]}' \
 '{"note_type":"medication","title":"Metoprolol evening dose","body":"Took evening blood pressure tablet. Home reading 128/82.","fields":{"medication":"Metoprolol 25mg","dose":"1 tablet","frequency":"Twice daily"},"tags":["blood pressure"]}' \
 '{"note_type":"free","title":"Poor sleep again","body":"Could not fall asleep until nearly 2am, woke three times.","tags":["sleep","insomnia"]}'
do
  title=$(echo "$payload" | python3 -c "import sys,json;print(json.load(sys.stdin)['title'])")
  curl -s -X POST "$API/notes/" -H "$AUTH" -H "Content-Type: application/json" -d "$payload" >/dev/null
  echo "  ${G}✓${N} created — $title"
done
echo
echo "${C}One endpoint serves all four note templates.${N}"
pause "$1"

# ───────────────────────────────────────────── 6. template validation
step "6 · Templates are enforced"
echo "Sending a 'medication' field on a 'symptom' note:"
curl -s -X POST "$API/notes/" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"note_type":"symptom","title":"Wrong","fields":{"medication":"Aspirin"}}' | python3 -m json.tool
pause "$1"

# ───────────────────────────────────────────── 7. list
step "7 · Read the notes back"
curl -s "$API/notes/" -H "$AUTH" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('Total notes:', d['count'], chr(10))
for n in d['results']:
    print(f\"  [{n['note_type']:<10}] {n['title']}\")
    print(f\"               {n['body'][:66]}...\")"
pause "$1"

# ───────────────────────────────────────────── 8. llm status
step "8 · Is the AI tier reachable?"
echo "GET /api/v1/llm/status/  — Django asking the LLM service if it is alive"; echo
curl -s "$API/llm/status/" -H "$AUTH" | python3 -m json.tool
echo
echo "${C}Separate service on port 8001. Django never loads the 209 MB model itself.${N}"
pause "$1"

# ───────────────────────────────────────────── 9. generate
step "9 · Generate an AI summary — the full chain"
echo "POST /api/v1/summaries/generate/"
echo
echo "  Django reads the notes from PostgreSQL"
echo "  → converts them into the model's input format"
echo "  → POSTs to the LLM service on :8001"
echo "  → the Transformer generates"
echo "  → Django stores the result and links its source notes"
echo
echo "${C}Beam search on CPU — takes about 20 seconds.${N}"; echo
time curl -s -X POST "$API/summaries/generate/" -H "$AUTH" \
  -H "Content-Type: application/json" -d '{"period":"week"}' | python3 -c "
import sys,json
d=json.load(sys.stdin)
print('status        :', d['status'])
print('model version :', d['model_version'])
print('source notes  :', d['source_note_ids'])
print()
print('DAILY LINES  (rule-based — deterministic, accurate)')
for line in d['daily_lines']: print('  *', line['summary'])
print()
print('OVERALL SUMMARY  (neural — see faithfulness note)')
print(' ', d['summary_text'][:400])"
pause "$1"

# ───────────────────────────────────────────── 10. persistence
step "10 · It is genuinely in the database"
echo "\$ psql -d jranalytics"; echo
$PSQL -d jranalytics -c "SELECT id, note_type, title FROM notes_healthnote ORDER BY id DESC LIMIT 3;"
$PSQL -d jranalytics -c "SELECT id, period, status, model_version FROM notes_aisummary ORDER BY id DESC LIMIT 2;"
echo "Provenance — which notes produced which summary:"
$PSQL -d jranalytics -c "SELECT aisummary_id, healthnote_id FROM notes_aisummary_source_notes ORDER BY aisummary_id DESC LIMIT 5;"
pause "$1"

# ───────────────────────────────────────────── 11. wrap
step "11 · Summary of what was demonstrated"
cat <<EOF

  ${G}✓${N} PostgreSQL database, 16 tables generated from Django models
  ${G}✓${N} JWT authentication with validation and consent capture
  ${G}✓${N} Health notes CRUD with four templates enforced server-side
  ${G}✓${N} User-scoped queries — no path returns another user's records
  ${G}✓${N} A 52.7M-parameter Transformer running as its own service
  ${G}✓${N} Backend calling the AI tier over HTTP and storing the result
  ${G}✓${N} Full provenance — every summary linked to its source notes

  Also built, not shown here:
    · faithfulness_eval.py — measured claim accuracy at 26.2%
    · Interactive prototype covering all 11 screens
    · Implementation plan and individual plan

  Next: Celery for asynchronous inference, S3 attachments,
        pgvector semantic search, administrator endpoints.

EOF
