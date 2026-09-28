from django.db import models
from django.conf import settings
import uuid


class Detection(models.Model):
    MEDIA_CHOICES = (
        ("image", "Image"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("text", "Text"),
        ("document", "Document"),
        ("link", "Link"),
        ("compare", "File Comparison"),
        ("proctor", "AI Interview Proctoring"),
        ("crawler", "Web & Media Monitor"),
        ("jobs", "Job Role Authenticator"),
        ("recruiter", "Recruiter Identity Authenticator"),
    )
    RESULT_CHOICES = (
        ("REAL", "Real"),
        ("FAKE", "Fake"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="detections")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    media_type = models.CharField(max_length=15, choices=MEDIA_CHOICES, default="image")

    original_filename = models.CharField(max_length=255)
    stored_filename = models.CharField(max_length=255, blank=True, null=True)
    file_hash = models.CharField(max_length=64, blank=True, null=True)  # SHA-256 hex digest
    result = models.CharField(max_length=10, choices=RESULT_CHOICES)
    confidence = models.FloatField()
    raw_probability = models.FloatField(blank=True, null=True)
    ela_filename = models.CharField(max_length=255, blank=True, null=True)
    gradcam_filename = models.CharField(max_length=255, blank=True, null=True)
    report_filename = models.CharField(max_length=255, blank=True, null=True)
    certificate_filename = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.media_type} - {self.result} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"

    @property
    def is_verified_authentic(self):
        """LOW risk documents and REAL results on everything else qualify for a certificate."""
        return self.result == "REAL"


class AgenticSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agentic_sessions")
    session_id = models.CharField(max_length=64, unique=True)
    media_file = models.FileField(upload_to="agent_uploads/", blank=True, null=True)
    original_filename = models.CharField(max_length=255, blank=True)
    detected_media_type = models.CharField(max_length=32, blank=True) # image, video, audio, document, text
    summary_verdict = models.CharField(max_length=32, blank=True) # REAL, FAKE, UNVERIFIED
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Agent Session {self.session_id[:8]} - {self.user.email} ({self.detected_media_type})"


class AgenticMessage(models.Model):
    SENDER_CHOICES = (
        ("user", "User"),
        ("agent", "VeriScan Agent"),
        ("system", "Tool System Trace"),
    )

    session = models.ForeignKey(AgenticSession, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=16, choices=SENDER_CHOICES)
    content = models.TextField()
    thought_trace = models.JSONField(default=list, blank=True) # Step-by-step tool thoughts
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.sender}] {self.content[:40]}..."


class MonitoredTarget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="monitored_targets")
    target_name = models.CharField(max_length=255)
    category = models.CharField(max_length=64, default="Person/Brand")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.target_name} ({self.user.email})"


class DiscoveredMediaSource(models.Model):
    target = models.ForeignKey(MonitoredTarget, on_delete=models.CASCADE, related_name="discovered_sources")
    source_name = models.CharField(max_length=255)
    domain = models.CharField(max_length=255)
    url = models.URLField(max_length=1024)
    title = models.CharField(max_length=512)
    snippet = models.TextField(blank=True)
    media_url = models.URLField(max_length=1024, blank=True)
    deepfake_result = models.CharField(max_length=32, default="UNVERIFIED") # REAL, FAKE, UNVERIFIED
    confidence = models.FloatField(default=0.0)
    discovered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-discovered_at"]

    def __str__(self):
        return f"[{self.domain}] {self.title[:30]} -> {self.deepfake_result}"


class JobSearchQuery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="job_searches")
    role_query = models.CharField(max_length=255)
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-searched_at"]

    def __str__(self):
        return f"Job Search: '{self.role_query}' ({self.user.email})"


class JobListingVerification(models.Model):
    query = models.ForeignKey(JobSearchQuery, on_delete=models.CASCADE, related_name="listings")
    job_title = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255)
    company_domain = models.CharField(max_length=255)
    source_platform = models.CharField(max_length=255, default="Official Careers Portal")
    location = models.CharField(max_length=255, default="Remote / Hybrid")

    posted_date = models.CharField(max_length=64, default="Recently")
    apply_url = models.URLField(max_length=1024)
    status = models.CharField(max_length=16, default="REAL") # REAL, FAKE
    confidence = models.FloatField(default=90.0)
    scam_indicators = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.job_title} at {self.company_name} [{self.status}]"


class RecruiterQuery(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recruiter_searches")
    recruiter_input = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True)
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-searched_at"]

    def __str__(self):
        return f"Recruiter Search: '{self.recruiter_input}' by {self.user.email}"


class RecruiterVerification(models.Model):
    query = models.ForeignKey(RecruiterQuery, on_delete=models.CASCADE, related_name="verifications")
    recruiter_name = models.CharField(max_length=255)
    claimed_company = models.CharField(max_length=255)
    profile_url = models.URLField(max_length=1024, blank=True)
    email_domain = models.CharField(max_length=255, default="unverified")
    
    authenticity_status = models.CharField(max_length=32, default="LEGITIMATE") # LEGITIMATE, FRAUDULENT_SUSPICIOUS, SYNTHETIC_IDENTITY
    confidence_score = models.FloatField(default=95.0)
    identity_signals = models.JSONField(default=list, blank=True)
    verified_sources = models.JSONField(default=list, blank=True)
    verified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.recruiter_name} ({self.claimed_company}) -> {self.authenticity_status}"



