from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Max, Count
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .models import SupportMessage, Feedback

User = get_user_model()



@login_required
def my_thread(request):
    """The user's own support chat with the admin team."""
    user = request.user
    if user.is_admin:
        return redirect("support:admin_thread_list")

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            SupportMessage.objects.create(thread_user=user, sender=user, body=body, read_by_user=True)
        return redirect("support:my_thread")

    SupportMessage.objects.filter(thread_user=user, sender__role="admin").update(read_by_user=True)

    thread = SupportMessage.objects.filter(thread_user=user).select_related("sender").order_by("created_at")
    return render(request, "support/my_thread.html", {"user": user, "thread": thread, "active_nav": "support"})


@login_required
def my_thread_poll(request):
    """Lightweight polling endpoint so the user's chat feels near-real-time without websockets."""
    user = request.user
    if user.is_admin:
        return JsonResponse({"messages": []})

    since_id = int(request.GET.get("since", 0) or 0)
    new_messages = SupportMessage.objects.filter(thread_user=user, id__gt=since_id).select_related("sender").order_by("created_at")
    data = [
        {
            "id": m.id, "body": m.body, "is_admin": m.is_from_admin,
            "sender_name": m.sender.name, "created_at": m.created_at.strftime("%b %d, %H:%M"),
        }
        for m in new_messages
    ]
    return JsonResponse({"messages": data})


@login_required
def admin_thread_list(request):
    if not request.user.is_admin:
        return redirect("detection:dashboard")

    threads = (
        User.objects.filter(role="user")
        .annotate(
            last_message_at=Max("support_thread__created_at"),
            unread_count=Count("support_thread", filter=Q(support_thread__read_by_admin=False, support_thread__sender__role="user")),
        )
        .filter(last_message_at__isnull=False)
        .order_by("-last_message_at")
    )
    return render(request, "support/admin_thread_list.html", {
        "user": request.user, "threads": threads, "active_nav": "admin_support",
    })


@login_required
def admin_thread_detail(request, user_id):
    if not request.user.is_admin:
        return redirect("detection:dashboard")

    thread_user = get_object_or_404(User, id=user_id, role="user")

    if request.method == "POST":
        body = request.POST.get("body", "").strip()
        if body:
            SupportMessage.objects.create(thread_user=thread_user, sender=request.user, body=body, read_by_admin=True)
        return redirect("support:admin_thread_detail", user_id=user_id)

    SupportMessage.objects.filter(thread_user=thread_user, sender__role="user").update(read_by_admin=True)

    thread = SupportMessage.objects.filter(thread_user=thread_user).select_related("sender").order_by("created_at")
    return render(request, "support/admin_thread_detail.html", {
        "user": request.user, "thread_user": thread_user, "thread": thread, "active_nav": "admin_support",
    })


@login_required
def admin_thread_poll(request, user_id):
    if not request.user.is_admin:
        return JsonResponse({"messages": []})

    thread_user = get_object_or_404(User, id=user_id, role="user")
    since_id = int(request.GET.get("since", 0) or 0)
    new_messages = SupportMessage.objects.filter(thread_user=thread_user, id__gt=since_id).select_related("sender").order_by("created_at")
    data = [
        {
            "id": m.id, "body": m.body, "is_admin": m.is_from_admin,
            "sender_name": m.sender.name, "created_at": m.created_at.strftime("%b %d, %H:%M"),
        }
        for m in new_messages
    ]
    return JsonResponse({"messages": data})


from django.core.mail import send_mail
from django.conf import settings

@login_required
def user_feedback(request):
    """View and submit feedback for regular users."""
    if request.method == "POST":
        category = request.POST.get("category", "general")
        rating = request.POST.get("rating", 5)
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()

        try:
            rating = int(rating)
            if not (1 <= rating <= 5):
                rating = 5
        except (ValueError, TypeError):
            rating = 5

        if subject and message:
            fb = Feedback.objects.create(
                user=request.user,
                category=category,
                rating=rating,
                subject=subject,
                message=message,
            )
            
            from accounts.utils import send_feedback_acknowledgement_email
            send_feedback_acknowledgement_email(request.user.email, request.user.name, fb.subject, fb.rating)
            
            admin_email = getattr(settings, "ADMIN_EMAIL", None)
            if admin_email:
                send_mail(
                    subject=f"New User Feedback: {fb.subject}",
                    message=f"User {request.user.email} submitted {fb.get_category_display()} feedback ({fb.rating} stars):\n\n{fb.message}",
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@veriscan.ai"),
                    recipient_list=[admin_email],
                    fail_silently=True,
                )

            messages.success(request, "Thank you! Your feedback has been submitted successfully and a thank you email has been sent.")

            return redirect("support:feedback")
        else:
            messages.error(request, "Please fill in all required fields (subject and message).")

    feedbacks = Feedback.objects.filter(user=request.user)
    return render(request, "support/feedback.html", {
        "user": request.user,
        "feedbacks": feedbacks,
        "active_nav": "feedback",
    })


