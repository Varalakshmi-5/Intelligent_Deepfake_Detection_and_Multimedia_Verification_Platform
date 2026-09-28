from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
from datetime import timedelta
import random


class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None, role="user", is_verified=False):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, name=name, role=role, is_verified=is_verified)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None):
        user = self.create_user(email, name, password, role="admin", is_verified=True)
        user.is_staff = True
        user.is_superuser = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ("user", "User"),
        ("admin", "Admin"),
    )

    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="user")
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    # --- Billing / access control ---
    free_detections_used = models.PositiveIntegerField(default=0)
    paid_access_until = models.DateTimeField(blank=True, null=True)

    # --- Face Biometric Verification ---
    face_descriptor = models.TextField(blank=True, null=True)
    face_registered = models.BooleanField(default=False)


    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def has_paid_access(self):
        return bool(self.paid_access_until and self.paid_access_until > timezone.now())

    @property
    def free_detections_remaining(self):
        from django.conf import settings
        return max(settings.FREE_DETECTION_LIMIT - self.free_detections_used, 0)

    @property
    def has_detection_access(self):
        """Admins always have access. Everyone else needs free credits or an active paid week."""
        if self.is_admin:
            return True
        return self.free_detections_remaining > 0 or self.has_paid_access

    def register_detection_used(self):
        from django.conf import settings
        if self.free_detections_used < settings.FREE_DETECTION_LIMIT:
            self.free_detections_used += 1
            self.save(update_fields=["free_detections_used"])

    def grant_paid_week(self, days=None):
        from django.conf import settings
        days = days or settings.PAID_ACCESS_DAYS
        base = self.paid_access_until if self.has_paid_access else timezone.now()
        self.paid_access_until = base + timedelta(days=days)
        self.save(update_fields=["paid_access_until"])


class OTP(models.Model):
    PURPOSE_CHOICES = (
        ("signup", "Signup Verification"),
        ("reset", "Password Reset"),
    )

    email = models.EmailField()
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=10, choices=PURPOSE_CHOICES)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_code():
        return f"{random.randint(0, 999999):06d}"

    @classmethod
    def issue(cls, email, purpose, expiry_minutes=10):
        code = cls.generate_code()
        otp = cls.objects.create(
            email=email.lower(),
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
        )
        return otp

    def is_valid(self, code):
        return (not self.used) and self.code == code and timezone.now() <= self.expires_at

    def __str__(self):
        return f"OTP({self.email}, {self.purpose})"
