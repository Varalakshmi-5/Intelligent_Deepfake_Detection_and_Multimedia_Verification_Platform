from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect


def admin_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to continue.")
            return redirect("accounts:landing")
        if not request.user.is_admin:
            messages.error(request, "You do not have permission to view this page.")
            return redirect("detection:dashboard")
        return view(request, *args, **kwargs)
    return wrapped
