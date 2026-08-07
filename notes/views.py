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
    """
    conditions, medications = set(), set()
    for n in notes:
        if n.note_type == HealthNote.Type.MEDICATION:
            medications.add(n.fields.get("medication", n.title))
        conditions.update(n.tags)

    age = ""
    if user.date_of_birth:
        age = str((timezone.now().date() - user.date_of_birth).days // 365)

    lines = [
        "patient Female" if False else "patient Male",   # extend when gender is captured
        f"age {age or 'unknown'}",
        f"conditions {', '.join(sorted(conditions)) or 'unspecified'}",
        f"prescribed {', '.join(sorted(medications)) or 'none'}",
        f"monitoring window {PERIOD_DAYS[period]} days",
        f"entries logged {len(notes)} of {PERIOD_DAYS[period]} days",
        "log:",
    ]

    for i, n in enumerate(sorted(notes, key=lambda x: x.created_at), start=1):
        parts = [f"day {i:02d}"]
        f = n.fields or {}
        if f.get("severity"):
            parts.append(f"severity {f['severity']}")
        if f.get("medication"):
            parts.append(f"meds {f['medication']}=Y")
        parts.append(f"symptoms {', '.join(n.tags) if n.tags else 'none'}")
        lines.append(" | ".join(parts))

    lines.append("summary")
    return "\n".join(lines)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def llm_status(request):
    """GET /api/v1/llm/status/ — is the AI tier reachable? Useful in the demo."""
    try:
        return Response({"reachable": True, **health()})
    except LLMUnavailable as exc:
        return Response({"reachable": False, "detail": str(exc)},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)
