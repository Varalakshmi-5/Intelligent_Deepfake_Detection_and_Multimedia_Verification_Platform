from .models import ActivityLog


def get_client_ip(request):
    if not request:
        return None
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


def log_activity(request, user=None, user_email="", action="", description=""):
    """
    Utility helper to log system security & user events cleanly.
    """
    try:
        email = user.email if (user and hasattr(user, "email") and user.email) else user_email
        ip_addr = get_client_ip(request)
        ua = request.META.get('HTTP_USER_AGENT', '')[:500] if request else ""

        ActivityLog.objects.create(
            user=user if (user and hasattr(user, "pk") and user.pk) else None,
            user_email=email,
            action=action,
            description=description,
            ip_address=ip_addr,
            user_agent=ua
        )
    except Exception as exc:
        print(f"[ACTIVITY LOG FAILED] {exc}")
