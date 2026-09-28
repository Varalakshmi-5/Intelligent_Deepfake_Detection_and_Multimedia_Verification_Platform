from django.db import models
from django.conf import settings


class PaymentRequest(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="payment_requests")
    utr_reference = models.CharField(
        max_length=64,
        help_text="The UPI transaction/reference number (UTR) shown in the user's payment app after paying.",
    )
    amount_claimed_inr = models.PositiveIntegerField(default=100)
    screenshot = models.ImageField(upload_to="payment_proofs/", blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True,
        related_name="reviewed_payment_requests",
    )
    admin_note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.user.email} - {self.utr_reference} - {self.status}"

    @property
    def amount_display(self):
        return f"₹{self.amount_claimed_inr}"
