from django.contrib import admin
from .models import Detection


@admin.register(Detection)
class DetectionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "media_type", "original_filename", "result", "confidence", "created_at")
    list_filter = ("media_type", "result")
    search_fields = ("original_filename", "user__email")
