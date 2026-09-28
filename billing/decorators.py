from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse


def requires_detection_access(view):
    """
    Gates a detection view behind the free-tier/paid-access check.
    Redirects to the paywall page (preserving where the user was headed)
    if they've used their free detections and have no active paid week.
    Admins always pass through.
    """
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:landing")
        if not request.user.has_detection_access:
            pay_url = reverse("billing:pay")
            return redirect(f"{pay_url}?next={request.path}")
        return view(request, *args, **kwargs)
    return wrapped
