from django.contrib import admin
from .models import PaymentRequest


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "utr_reference", "amount_display", "status", "submitted_at", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("user__email", "utr_reference")
