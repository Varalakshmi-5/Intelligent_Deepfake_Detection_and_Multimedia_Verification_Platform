from django.db import models
from django.conf import settings


class ActivityLog(models.Model):
    ACTION_CHOICES = (
        ("login_success", "Login Success"),
        ("login_failed", "Login Failed"),
        ("logout", "Logout"),
        ("face_verified", "Face Verified & Registered"),
        ("face_rejected", "Duplicate Face Rejected"),
        ("detection_run", "Detection Executed"),
        ("payment_submitted", "Payment Request Submitted"),
        ("payment_approved", "Payment Request Approved"),
        ("payment_rejected", "Payment Request Rejected"),
        ("access_granted", "Access Granted by Admin"),
        ("user_disabled", "User Disabled"),
        ("user_enabled", "User Enabled"),
        ("user_deleted", "User Deleted"),
        ("password_reset", "Password Reset"),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="activity_logs"
    )
    user_email = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=512, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.user_email or 'Anonymous'} - {self.get_action_display()}"
