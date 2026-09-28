import os
from django.conf import settings as dj_settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.mail import send_mail


from accounts.forms import validate_password_strength
from detection.models import Detection
from billing.models import PaymentRequest
from support.models import Feedback
from .decorators import admin_required


User = get_user_model()


@login_required
@admin_required
def dashboard(request):
    total_users = User.objects.filter(role="user").count()
    verified_users = User.objects.filter(role="user", is_verified=True).count()
    total_detections = Detection.objects.count()
    fake_count = Detection.objects.filter(result="FAKE").count()
    real_count = Detection.objects.filter(result="REAL").count()
    unverified_count = max(0, total_detections - (real_count + fake_count))

    by_media = Detection.objects.values("media_type").annotate(count=Count("id")).order_by("-count")
    recent_detections = Detection.objects.select_related("user").order_by("-created_at")[:8]

    media_chart_labels = [m["media_type"].capitalize() for m in by_media]
    media_chart_data = [m["count"] for m in by_media]

    return render(request, "adminpanel/dashboard.html", {
        "user": request.user,
        "active_nav": "admin_dashboard",
        "total_users": total_users,
        "verified_users": verified_users,
        "total_detections": total_detections,
        "fake_count": fake_count,
        "real_count": real_count,
        "unverified_count": unverified_count,
        "by_media": by_media,
        "recent_detections": recent_detections,
        "media_chart_labels": media_chart_labels,
        "media_chart_data": media_chart_data,
    })



@login_required
@admin_required
def manage_users(request):
    query = request.GET.get("q", "").strip()
    users = User.objects.filter(role="user")
    if query:
        users = users.filter(Q(name__icontains=query) | Q(email__icontains=query))
    users = users.annotate(detection_count=Count("detections")).order_by("-date_joined")
    return render(request, "adminpanel/manage_users.html", {
        "user": request.user, "users": users, "query": query, "active_nav": "admin_users",
    })


@login_required
@admin_required
@require_http_methods(["POST"])
def toggle_user_active(request, user_id):
    from .utils import log_activity
    target = get_object_or_404(User, id=user_id, role="user")
    target.is_active = not target.is_active
    target.save()
    status_str = "enabled" if target.is_active else "disabled"
    log_activity(
        request,
        user=request.user,
        action=f"user_{status_str}",
        description=f"Admin {request.user.email} {status_str} account for '{target.email}'."
    )
    messages.success(request, f"{target.email} has been {status_str}.")
    return redirect("adminpanel:manage_users")


@login_required
@admin_required
@require_http_methods(["POST"])
def grant_access(request, user_id):
    from .utils import log_activity
    target = get_object_or_404(User, id=user_id, role="user")
    target.grant_paid_week()
    from accounts.utils import send_payment_approval_email
    send_payment_approval_email(target.email, target.name, days_granted=7)
    log_activity(
        request,
        user=request.user,
        action="access_granted",
        description=f"Admin granted 7 extra access days to user '{target.email}'."
    )
    messages.success(request, f"Granted {target.email} 7 more days of unlimited access.")
    return redirect("adminpanel:manage_users")


@login_required
@admin_required
@require_http_methods(["POST"])
def delete_user(request, user_id):
    from .utils import log_activity
    target = get_object_or_404(User, id=user_id, role="user")
    email = target.email
    log_activity(
        request,
        user=request.user,
        user_email=email,
        action="user_deleted",
        description=f"Admin permanently deleted user account '{email}'."
    )
    target.delete()
    messages.success(request, f"Deleted user {email} and their detection history.")
    return redirect("adminpanel:manage_users")



@login_required
@admin_required
def all_detections(request):
    query = request.GET.get("q", "").strip()
    media_filter = request.GET.get("media", "").strip()
    result_filter = request.GET.get("result", "").strip()

    detections = Detection.objects.select_related("user").all()
    if query:
        detections = detections.filter(
            Q(original_filename__icontains=query) | Q(user__email__icontains=query)
        )
    if media_filter:
        detections = detections.filter(media_type=media_filter)
    if result_filter:
        detections = detections.filter(result=result_filter)

    detections = detections.order_by("-created_at")

    return render(request, "adminpanel/detections.html", {
        "user": request.user,
        "detections": detections,
        "query": query,
        "media_filter": media_filter,
        "result_filter": result_filter,
        "active_nav": "admin_detections",
    })


@login_required
@admin_required
def download_report(request, detection_id):
    detection = get_object_or_404(Detection, id=detection_id)
    if not detection.report_filename:
        raise Http404("Report not found.")
    report_path = os.path.join(dj_settings.REPORT_DIR, detection.report_filename)
    if not os.path.exists(report_path):
        raise Http404("Report file missing.")
    return FileResponse(
        open(report_path, "rb"), as_attachment=True,
        filename=f"deepfake_report_{detection.original_filename}.pdf",
    )


@login_required
@admin_required
def admin_settings(request):
    admin_user = request.user

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        email = request.POST.get("email", "").strip().lower()
        new_password = request.POST.get("new_password", "").strip()

        if not name or not email:
            messages.error(request, "Name and email are required.")
            return redirect("adminpanel:settings")

        if User.objects.filter(email=email).exclude(id=admin_user.id).exists():
            messages.error(request, "That email is already in use.")
            return redirect("adminpanel:settings")

        admin_user.name = name
        admin_user.email = email

        if new_password:
            try:
                validate_password_strength(new_password)
            except Exception as exc:
                messages.error(request, str(exc.messages[0]) if hasattr(exc, "messages") else str(exc))
                return redirect("adminpanel:settings")
            admin_user.set_password(new_password)

        admin_user.save()
        messages.success(request, "Admin profile updated successfully.")

        if new_password:
            from django.contrib.auth import login as auth_login
            auth_login(request, admin_user, backend="accounts.backends.EmailBackend")

        return redirect("adminpanel:settings")

    return render(request, "adminpanel/settings.html", {"user": admin_user, "active_nav": "admin_settings"})


@login_required
@admin_required
def payment_requests(request):
    status_filter = request.GET.get("status", "pending")
    requests_qs = PaymentRequest.objects.select_related("user").all()
    if status_filter and status_filter != "all":
        requests_qs = requests_qs.filter(status=status_filter)
    requests_qs = requests_qs.order_by("-submitted_at")

    pending_count = PaymentRequest.objects.filter(status="pending").count()

    return render(request, "adminpanel/payment_requests.html", {
        "user": request.user,
        "payment_requests": requests_qs,
        "status_filter": status_filter,
        "pending_count": pending_count,
        "active_nav": "admin_payments",
    })


@login_required
@admin_required
@require_http_methods(["POST"])
def approve_payment_request(request, request_id):
    from .utils import log_activity
    payment_request = get_object_or_404(PaymentRequest, id=request_id)
    if payment_request.status != "pending":
        messages.error(request, "This request has already been reviewed.")
        return redirect("adminpanel:payment_requests")

    payment_request.status = "approved"
    payment_request.reviewed_at = timezone.now()
    payment_request.reviewed_by = request.user
    payment_request.save()

    payment_request.user.grant_paid_week()

    from accounts.utils import send_payment_approval_email
    send_payment_approval_email(payment_request.user.email, payment_request.user.name, days_granted=dj_settings.PAID_ACCESS_DAYS)

    log_activity(
        request,
        user=request.user,
        action="payment_approved",
        description=f"Admin approved UPI payment request of ₹{payment_request.amount_claimed_inr} for user '{payment_request.user.email}' (Ref: {payment_request.utr_reference})."
    )

    messages.success(request, f"Approved payment for {payment_request.user.email} — {dj_settings.PAID_ACCESS_DAYS} days granted and notification email sent.")
    return redirect("adminpanel:payment_requests")


@login_required
@admin_required
@require_http_methods(["POST"])
def reject_payment_request(request, request_id):
    from .utils import log_activity
    payment_request = get_object_or_404(PaymentRequest, id=request_id)
    if payment_request.status != "pending":
        messages.error(request, "This request has already been reviewed.")
        return redirect("adminpanel:payment_requests")

    payment_request.status = "rejected"
    payment_request.reviewed_at = timezone.now()
    payment_request.reviewed_by = request.user
    payment_request.admin_note = request.POST.get("reason", "").strip()
    payment_request.save()

    send_mail(
        subject="VeriScan AI - Payment Request Update",
        message=f"Hi {payment_request.user.name},\n\nYour payment request (Ref: {payment_request.utr_reference}) could not be approved at this time.\nReason: {payment_request.admin_note or 'Verification details incomplete.'}\n\nPlease contact support or resubmit if you believe this is an error.",
        from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", "noreply@veriscan.ai"),
        recipient_list=[payment_request.user.email],
        fail_silently=True,
    )

    log_activity(
        request,
        user=request.user,
        action="payment_rejected",
        description=f"Admin rejected UPI payment request for '{payment_request.user.email}' (Ref: {payment_request.utr_reference}). Reason: {payment_request.admin_note or 'None provided'}."
    )

    messages.success(request, f"Rejected payment request from {payment_request.user.email} and notification email sent.")
    return redirect("adminpanel:payment_requests")




@login_required
@admin_required
def all_feedbacks(request):
    """Admin view to list and filter all user submitted feedbacks."""
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    rating = request.GET.get("rating", "").strip()
    status = request.GET.get("status", "").strip()

    feedbacks = Feedback.objects.select_related("user").all()

    if query:
        feedbacks = feedbacks.filter(
            Q(user__email__icontains=query) |
            Q(user__name__icontains=query) |
            Q(subject__icontains=query) |
            Q(message__icontains=query)
        )
    if category:
        feedbacks = feedbacks.filter(category=category)
    if rating:
        try:
            feedbacks = feedbacks.filter(rating=int(rating))
        except ValueError:
            pass
    if status == "reviewed":
        feedbacks = feedbacks.filter(is_reviewed=True)
    elif status == "unreviewed":
        feedbacks = feedbacks.filter(is_reviewed=False)

    total_feedbacks = Feedback.objects.count()
    unreviewed_count = Feedback.objects.filter(is_reviewed=False).count()
    avg_rating_res = Feedback.objects.aggregate(Avg("rating"))["rating__avg"]
    avg_rating = round(avg_rating_res, 1) if avg_rating_res else 0.0

    # Chart datasets
    rating_data = [Feedback.objects.filter(rating=r).count() for r in [5, 4, 3, 2, 1]]
    cat_keys = ["general", "bug", "feature", "accuracy", "other"]
    cat_labels = ["General", "Bug Report", "Feature Request", "Accuracy", "Other"]
    category_data = [Feedback.objects.filter(category=c).count() for c in cat_keys]

    return render(request, "adminpanel/feedbacks.html", {
        "user": request.user,
        "feedbacks": feedbacks,
        "query": query,
        "category": category,
        "rating": rating,
        "status": status,
        "total_feedbacks": total_feedbacks,
        "unreviewed_count": unreviewed_count,
        "avg_rating": avg_rating,
        "rating_chart_data": rating_data,
        "category_chart_labels": cat_labels,
        "category_chart_data": category_data,
        "active_nav": "admin_feedbacks",
    })



@login_required
@admin_required
@require_http_methods(["POST"])
def toggle_feedback_reviewed(request, feedback_id):
    feedback = get_object_or_404(Feedback, id=feedback_id)
    feedback.is_reviewed = not feedback.is_reviewed
    feedback.save()
    status_str = "reviewed" if feedback.is_reviewed else "pending"
    messages.success(request, f"Feedback #{feedback.id} marked as {status_str}.")
    return redirect("adminpanel:all_feedbacks")


@login_required
@admin_required
@require_http_methods(["POST"])
def add_feedback_notes(request, feedback_id):
    feedback = get_object_or_404(Feedback, id=feedback_id)
    notes = request.POST.get("admin_notes", "").strip()
    feedback.admin_notes = notes
    feedback.is_reviewed = True
    feedback.save()

    if feedback.user and feedback.user.email:
        send_mail(
            subject=f"VeriScan AI - Response to your feedback: {feedback.subject}",
            message=f"Hi {feedback.user.name},\n\nAn admin has reviewed and responded to your feedback on '{feedback.subject}':\n\nAdmin Response:\n\"{notes}\"\n\nThank you for helping us improve VeriScan AI!\n\nBest regards,\nVeriScan AI Team",
            from_email=getattr(dj_settings, "DEFAULT_FROM_EMAIL", "noreply@veriscan.ai"),
            recipient_list=[feedback.user.email],
            fail_silently=True,
        )

    messages.success(request, f"Response saved for feedback #{feedback.id} and email notification sent to user.")
    return redirect("adminpanel:all_feedbacks")



@login_required
@admin_required
@require_http_methods(["POST"])
def delete_feedback(request, feedback_id):
    feedback = get_object_or_404(Feedback, id=feedback_id)
    feedback.delete()
    messages.success(request, "Feedback entry deleted.")
    return redirect("adminpanel:all_feedbacks")


@login_required
@admin_required
def audit_logs(request):
    import csv
    from django.core.paginator import Paginator
    from .models import ActivityLog

    query = request.GET.get("q", "").strip()
    action_filter = request.GET.get("action", "").strip()

    logs = ActivityLog.objects.select_related("user").all()

    if query:
        logs = logs.filter(
            Q(user_email__icontains=query) |
            Q(description__icontains=query) |
            Q(ip_address__icontains=query)
        )

    if action_filter:
        logs = logs.filter(action=action_filter)

    paginator = Paginator(logs, 25)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    action_choices = ActivityLog.ACTION_CHOICES

    return render(request, "adminpanel/audit_logs.html", {
        "user": request.user,
        "logs": page_obj,
        "query": query,
        "action_filter": action_filter,
        "action_choices": action_choices,
        "total_count": paginator.count,
        "active_nav": "admin_audit_logs",
    })


@login_required
@admin_required
def export_audit_logs_csv(request):
    import csv
    from django.http import HttpResponse
    from .models import ActivityLog

    query = request.GET.get("q", "").strip()
    action_filter = request.GET.get("action", "").strip()

    logs = ActivityLog.objects.select_related("user").all()

    if query:
        logs = logs.filter(
            Q(user_email__icontains=query) |
            Q(description__icontains=query) |
            Q(ip_address__icontains=query)
        )

    if action_filter:
        logs = logs.filter(action=action_filter)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="veriscan_audit_logs.csv"'

    writer = csv.writer(response)
    writer.writerow(["Timestamp (UTC)", "User Email", "Action", "Description", "IP Address", "User Agent"])

    for log in logs[:2000]:
        writer.writerow([
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            log.user_email or "Anonymous",
            log.get_action_display(),
            log.description,
            log.ip_address or "-",
            log.user_agent or "-",
        ])

    return response


