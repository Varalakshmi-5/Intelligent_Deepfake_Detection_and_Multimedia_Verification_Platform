from django.contrib import admin
from .models import SupportMessage, Feedback


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = ("thread_user", "sender", "body", "created_at", "read_by_admin", "read_by_user")
    list_filter = ("read_by_admin", "read_by_user")
    search_fields = ("thread_user__email", "sender__email", "body")


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("user", "category", "rating", "subject", "is_reviewed", "created_at")
    list_filter = ("category", "rating", "is_reviewed", "created_at")
    search_fields = ("user__email", "subject", "message")
    list_editable = ("is_reviewed",)

