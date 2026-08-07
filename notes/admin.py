from django.contrib import admin

from .models import AISummary, Attachment, HealthNote


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


@admin.register(HealthNote)
class HealthNoteAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "note_type", "created_at")
    list_filter = ("note_type", "created_at")
    search_fields = ("title", "body")
    inlines = [AttachmentInline]
    date_hierarchy = "created_at"


@admin.register(AISummary)
class AISummaryAdmin(admin.ModelAdmin):
    list_display = ("user", "period", "status", "model_version", "generated_at")
    list_filter = ("period", "status")
    filter_horizontal = ("source_notes",)
    readonly_fields = ("generated_at",)
