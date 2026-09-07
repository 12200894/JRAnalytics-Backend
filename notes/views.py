import re
from datetime import timedelta

from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .llm_client import LLMUnavailable, health, summarise
from .models import AISummary, HealthNote
from .serializers import AISummarySerializer, HealthNoteSerializer

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


class HealthNoteViewSet(viewsets.ModelViewSet):
    """
    /api/v1/notes/ — list, create, retrieve, update, delete.

    The queryset is filtered by user here rather than in each view, so there is no
    code path that can return another user's record.
    """
    serializer_class = HealthNoteSerializer

    def get_queryset(self):
        qs = HealthNote.objects.filter(user=self.request.user).prefetch_related("attachments")
        note_type = self.request.query_params.get("type")
        if note_type:
            qs = qs.filter(note_type=note_type)
        search = self.request.query_params.get("q")
        if search:
            # Keyword search for now. Semantic retrieval replaces this in Sprint 3.
            qs = qs.filter(title__icontains=search) | qs.filter(body__icontains=search)
        return qs.distinct()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class AISummaryViewSet(viewsets.ReadOnlyModelViewSet):
    """/api/v1/summaries/ — read past summaries, or generate a new one."""
    serializer_class = AISummarySerializer

    def get_queryset(self):
        return AISummary.objects.filter(user=self.request.user).prefetch_related("source_notes")

    @action(detail=False, methods=["post"])
    def generate(self, request):
        """
        POST /api/v1/summaries/generate/  {"period": "week"}

        Collects the user's notes for the period, renders them into the log format the
        model expects, calls the LLM service, and stores the result with its source notes
        so every statement stays traceable.
        """
        period = request.data.get("period", "week")
        if period not in PERIOD_DAYS:
            return Response({"period": f"Must be one of {list(PERIOD_DAYS)}."},
                            status=status.HTTP_400_BAD_REQUEST)

        since = timezone.now() - timedelta(days=PERIOD_DAYS[period])
        notes = list(HealthNote.objects.filter(user=request.user, created_at__gte=since))
        if not notes:
            return Response({"detail": f"No notes recorded in the last {PERIOD_DAYS[period]} days."},
                            status=status.HTTP_400_BAD_REQUEST)

        summary = AISummary.objects.create(user=request.user, period=period,
                                           status=AISummary.Status.PENDING)
        try:
            result = summarise(render_note_log(request.user, notes, period))
        except LLMUnavailable as exc:
            summary.status = AISummary.Status.FAILED
            summary.error = str(exc)
            summary.save(update_fields=["status", "error"])
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        summary.summary_text = result.get("overall", "")
        summary.daily_lines = result.get("daily", [])
        summary.model_version = result.get("model_version", "")
        summary.status = AISummary.Status.COMPLETE
        summary.save()
        summary.source_notes.set(notes)

        return Response(AISummarySerializer(summary).data, status=status.HTTP_201_CREATED)


def render_note_log(user, notes, period):
    """
    Turn stored notes into the plain-text log format the v11 model was trained on.

    The model expects header lines, then 'log:', then 'day NN | ...' rows, then a
    closing 'summary' line which triggers generation.

    Integration fix (7 Sept): the first version emitted one 'day' row per *note* and
    ignored every vitals field, so the model received lines like
    'day 01 | symptoms hypertension' with no numbers at all — and invented them.
    Now notes are grouped by calendar day and rendered with the exact tokens the
    model's parser understands (bp_am, hr, spo2, temp, symptoms, meds NAME=Y), so
    the rule-based daily lines are accurate and the model has real values to cite.
    """
    window_days = PERIOD_DAYS[period]

    conditions, medications = set(), set()
    for n in notes:
        if n.note_type == HealthNote.Type.MEDICATION:
            medications.add(_med_name(n))
        conditions.update(t.strip().lower() for t in (n.tags or []) if t and t.strip())

    age = ""
    if user.date_of_birth:
        age = str((timezone.now().date() - user.date_of_birth).days // 365)

    # Group by local calendar day so several notes on one day become one log row.
    by_day = {}
    for n in notes:
        by_day.setdefault(timezone.localtime(n.created_at).date(), []).append(n)
    days = sorted(by_day)

    lines = [
        "patient Male",   # extend when gender is captured
        f"age {age or 'unknown'}",
        f"conditions {', '.join(sorted(conditions)) or 'unspecified'}",
        f"prescribed {', '.join(sorted(medications)) or 'none'}",
        f"monitoring window {window_days} days",
        f"entries logged {len(days)} of {window_days} days",
        "log:",
    ]

    for i, day in enumerate(days, start=1):
        lines.append(_render_day(i, by_day[day]))

    lines.append("summary")
    return "\n".join(lines)


def _med_name(note):
    """Medication display name: the 'medication' template field, else the title."""
    f = note.fields or {}
    return (f.get("medication") or note.title or "").strip().lower()


def _render_day(day_no, day_notes):
    """One 'day NN | ...' row in the token order the model was trained on."""
    vitals, symptoms, meds = {}, [], []

    for n in day_notes:
        f = n.fields or {}
        if n.note_type == HealthNote.Type.VITALS:
            # Model keys: bp_am, hr, spo2, temp. Keep the last value logged that day.
            if f.get("blood_pressure"):
                vitals["bp_am"] = str(f["blood_pressure"]).strip()
            if f.get("heart_rate"):
                vitals["hr"] = _int_str(f["heart_rate"])
            if f.get("spo2"):
                vitals["spo2"] = _int_str(f["spo2"])
            if f.get("temperature"):
                vitals["temp"] = str(f["temperature"]).strip()
        elif n.note_type == HealthNote.Type.SYMPTOM:
            label = (n.title or "symptom").strip().lower()
            if f.get("severity"):
                label += f" ({str(f['severity']).strip()})"
            symptoms.append(label)
        elif n.note_type == HealthNote.Type.MEDICATION:
            name = _med_name(n)
            if name:
                meds.append(f"{name}=Y")

    parts = [f"day {day_no:02d}"]
    for key in ("bp_am", "hr", "spo2", "temp"):
        if vitals.get(key):
            parts.append(f"{key} {vitals[key]}")
    parts.append(f"symptoms {', '.join(symptoms) if symptoms else 'none'}")
    if meds:
        parts.append("meds " + " ".join(meds))
    return " | ".join(parts)


def _int_str(value):
    """'74', '74.0', ' 74 bpm' -> '74'; anything unparsable is passed through stripped."""
    m = re.search(r"\d+", str(value))
    return m.group(0) if m else str(value).strip()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def llm_status(request):
    """GET /api/v1/llm/status/ — is the AI tier reachable? Useful in the demo."""
    try:
        return Response({"reachable": True, **health()})
    except LLMUnavailable as exc:
        return Response({"reachable": False, "detail": str(exc)},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
