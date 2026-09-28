from django.db import models
from django.conf import settings


class SupportMessage(models.Model):
    """
    Every message belongs to a thread identified by `thread_user` — the
    regular (non-admin) user the conversation is with. `sender` is
    whoever actually wrote this particular message (could be the user
    themselves, or any admin replying). This keeps the model simple:
    one thread per user, any admin can view/reply to any thread.
    """
    thread_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_thread",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_support_messages",
    )
    body = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_by_admin = models.BooleanField(default=False)
    read_by_user = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.thread_user.email} <- {self.sender.email}: {self.body[:40]}"

    @property
    def is_from_admin(self):
        return self.sender.is_admin


class Feedback(models.Model):
    CATEGORY_CHOICES = [
        ("general", "General Feedback"),
        ("bug", "Bug Report"),
        ("feature", "Feature Request"),
        ("accuracy", "Detection Accuracy"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedbacks"
    )
    category = models.CharField(max_length=50, choices=CATEGORY_CHOICES, default="general")
    rating = models.PositiveSmallIntegerField(default=5)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    is_reviewed = models.BooleanField(default=False)
    admin_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Feedback ({self.category}, {self.rating}★) by {self.user.email}: {self.subject}"

