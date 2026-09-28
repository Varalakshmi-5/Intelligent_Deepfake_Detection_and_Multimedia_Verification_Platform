from django.apps import AppConfig
from django.db.models.signals import post_migrate


def bootstrap_admin(sender, **kwargs):
    """
    Ensures a default admin account (from .env) always exists after
    migrations run. If ADMIN_PASSWORD in .env changes, syncs it too,
    so redeploying with new .env values keeps the default admin usable.
    Admin can change name/email/password afterwards from the Admin
    Settings page in the app.
    """
    from django.conf import settings
    from django.contrib.auth import get_user_model

    User = get_user_model()

    existing = User.objects.filter(role="admin").order_by("id").first()
    if existing is None:
        User.objects.create_superuser(
            email=settings.DEFAULT_ADMIN_EMAIL,
            name=settings.DEFAULT_ADMIN_NAME,
            password=settings.DEFAULT_ADMIN_PASSWORD,
        )
        print(f"[SETUP] Default admin account created: {settings.DEFAULT_ADMIN_EMAIL}")


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        post_migrate.connect(bootstrap_admin, sender=self)
