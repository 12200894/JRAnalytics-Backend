"""
Seed a realistic 7-day demo account so the AI summary has real vitals to work with.

    ./venv/bin/python seed_demo.py            # creates demo@jranalytics.com / Demo!Pass2026
"""
import os, sys
from datetime import datetime, time, timedelta
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jranalytics.settings"); django.setup()
from django.utils import timezone
from accounts.models import User
from notes.models import HealthNote

EMAIL, PASSWORD = "demo@jranalytics.com", "Demo!Pass2026"
u, created = User.objects.get_or_create(email=EMAIL, defaults={"full_name": "Demo Patient"})
if created:
    u.set_password(PASSWORD); u.date_of_birth = timezone.now().date() - timedelta(days=62*365); u.save()
HealthNote.objects.filter(user=u).delete()

now = timezone.now()
DAYS = [  # days ago, bp, hr, spo2, temp, symptoms, took_med
    (6, "138/86", 74, 97, "36.7", [],                              True),
    (5, "141/88", 76, 97, "36.8", ["headache (4/10)"],             True),
    (4, "145/89", 78, 96, "36.9", ["headache (6/10)"],             False),
    (3, "152/94", 84, 96, "37.1", ["headache (7/10)", "dizziness (5/10)"], False),
    (2, "139/87", 75, 97, "36.8", [],                              True),
    (1, "136/84", 72, 98, "36.6", [],                              True),
]
def mk(days_ago, hour, **kw):
    n = HealthNote.objects.create(user=u, **kw)
    day = timezone.localtime(now).date() - timedelta(days=days_ago)
    stamp = timezone.make_aware(datetime.combine(day, time(hour=hour)))
    HealthNote.objects.filter(pk=n.pk).update(created_at=stamp)
for d, bp, hr, spo2, temp, symps, took in DAYS:
    mk(d, 9, note_type="vitals", title="Morning vitals", tags=["hypertension"],
       fields={"heart_rate": str(hr), "blood_pressure": bp, "spo2": str(spo2), "temperature": temp})
    for s in symps:
        name, sev = s.split(" (")
        mk(d, 6, note_type="symptom", title=name.capitalize(), body="", tags=[name],
           fields={"severity": sev.rstrip(")"), "duration": "2 hours", "triggers": "unknown"})
    if took:
        mk(d, 8, note_type="medication", title="Amlodipine", fields={"medication": "amlodipine 5mg", "dose": "5mg", "frequency": "daily"})
mk(3, 2, note_type="appointment", title="GP visit", fields={"clinician": "Dr Singh", "date": (now-timedelta(days=3)).date().isoformat(), "outcome": "Review BP in one week"})
mk(0, 7, note_type="free", title="Feeling better", body="Headache gone since restarting tablets.")
print(f"Seeded {HealthNote.objects.filter(user=u).count()} notes for {EMAIL} / {PASSWORD}")
