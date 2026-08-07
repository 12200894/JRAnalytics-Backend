"""
Health notes, attachments and AI summaries.

Mirrors the class diagram from ICT728: one User has many HealthNotes; a HealthNote
has many Attachments; an AISummary is generated from one or more HealthNotes.
"""

from django.conf import settings
from django.db import models


class HealthNote(models.Model):
    """A single health record entry, free-form or against a template."""

    class Type(models.TextChoices):
        FREE = "free", "Free-form"
        SYMPTOM = "symptom", "Symptom"
        MEDICATION = "medication", "Medication"
        APPOINTMENT = "appointment", "Appointment"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="notes")
    note_type = models.CharField(max_length=16, choices=Type.choices, default=Type.FREE)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)

    # Template values live in JSONB. One column serves all four note types, so adding
    # a template later needs no migration — a serializer change is enough.
    fields = models.JSONField(default=dict, blank=True)

    tags = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Almost every query filters on user and sorts by recency, so index both together.
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.user.email})"


class Attachment(models.Model):
    """A photo or PDF attached to a note."""

    class Kind(models.TextChoices):
        IMAGE = "image", "Image"
        PDF = "pdf", "PDF document"

    note = models.ForeignKey(HealthNote, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/%Y/%m/")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    original_name = models.CharField(max_length=255)
    size_bytes = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.original_name


class AISummary(models.Model):
    """
    A summary produced by the LLM service.

    Stores the source notes it was generated from, so every statement stays traceable
    back to the user's own records — the provenance requirement from the ethics section.
    """

    class Period(models.TextChoices):
        DAY = "day", "Day"
        WEEK = "week", "Week"
        MONTH = "month", "Month"
        YEAR = "year", "Year"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETE = "complete", "Complete"
        FAILED = "failed", "Failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="summaries")
    period = models.CharField(max_length=8, choices=Period.choices, default=Period.WEEK)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)

    summary_text = models.TextField(blank=True)
    daily_lines = models.JSONField(default=list, blank=True)   # rule-based, one entry per logged day
    source_notes = models.ManyToManyField(HealthNote, related_name="summaries", blank=True)

    model_version = models.CharField(max_length=32, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-generated_at"]
        verbose_name_plural = "AI summaries"

    def __str__(self):
        return f"{self.get_period_display()} summary — {self.user.email}"
