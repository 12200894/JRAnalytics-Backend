from rest_framework import serializers

from .models import AISummary, Attachment, HealthNote

# Required fields per note template. Free-form notes have none.
TEMPLATE_FIELDS = {
    HealthNote.Type.SYMPTOM: ["severity", "duration", "triggers"],
    HealthNote.Type.MEDICATION: ["medication", "dose", "frequency"],
    HealthNote.Type.APPOINTMENT: ["clinician", "date", "outcome"],
    HealthNote.Type.FREE: [],
}


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attachment
        fields = ("id", "file", "kind", "original_name", "size_bytes", "uploaded_at")
        read_only_fields = ("id", "uploaded_at", "size_bytes")


class HealthNoteSerializer(serializers.ModelSerializer):
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = HealthNote
        fields = ("id", "note_type", "title", "body", "fields", "tags",
                  "attachments", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")

    def validate(self, data):
        """One endpoint serves all four note types; the template decides what is allowed."""
        note_type = data.get("note_type", getattr(self.instance, "note_type", HealthNote.Type.FREE))
        allowed = TEMPLATE_FIELDS[note_type]
        supplied = data.get("fields", {}) or {}

        if not isinstance(supplied, dict):
            raise serializers.ValidationError({"fields": "Must be an object."})

        unexpected = set(supplied) - set(allowed)
        if unexpected:
            raise serializers.ValidationError(
                {"fields": f"Not valid for a '{note_type}' note: {', '.join(sorted(unexpected))}. "
                           f"Allowed: {', '.join(allowed) or 'none'}."})

        if not data.get("title") and not data.get("body"):
            raise serializers.ValidationError("Provide a title or a body.")
        return data


class AISummarySerializer(serializers.ModelSerializer):
    source_note_ids = serializers.PrimaryKeyRelatedField(
        source="source_notes", many=True, read_only=True)

    class Meta:
        model = AISummary
        fields = ("id", "period", "status", "summary_text", "daily_lines",
                  "source_note_ids", "model_version", "generated_at", "error")
        read_only_fields = fields
