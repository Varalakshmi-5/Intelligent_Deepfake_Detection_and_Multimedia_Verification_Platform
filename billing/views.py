from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse

from .models import PaymentRequest
from .upi_qr import generate_upi_qr_data_uri


@login_required
def pay(request):
    """
    The paywall page. Shown when a user's free detections are used up and
    they have no active paid week. Shows a UPI QR code to pay, and a form
    to submit the transaction reference for manual admin approval.
    """
    user = request.user
    if user.has_detection_access:
        next_url = request.GET.get("next") or reverse("detection:dashboard")
        return redirect(next_url)

    next_url = request.GET.get("next", "")

    if request.method == "POST":
        utr = request.POST.get("utr_reference", "").strip()
        screenshot = request.FILES.get("screenshot")

        if not utr:
            messages.error(request, "Please enter the UPI transaction/reference number.")
            return redirect(f"{reverse('billing:pay')}?next={next_url}")

        if PaymentRequest.objects.filter(user=user, status="pending").exists():
            messages.error(request, "You already have a payment awaiting approval. Please wait for it to be reviewed.")
            return redirect(f"{reverse('billing:pay')}?next={next_url}")

        PaymentRequest.objects.create(
            user=user,
            utr_reference=utr,
            amount_claimed_inr=settings.PAID_ACCESS_PRICE_INR,
            screenshot=screenshot,
        )
        from adminpanel.utils import log_activity
        log_activity(
            request,
            user=user,
            action="payment_submitted",
            description=f"User submitted UPI payment proof of ₹{settings.PAID_ACCESS_PRICE_INR} (Ref: {utr}) for admin approval."
        )
        messages.success(request, "Payment submitted! An admin will review it shortly and unlock your access.")
        return redirect(f"{reverse('billing:pay')}?next={next_url}")

    pending_request = PaymentRequest.objects.filter(user=user, status="pending").order_by("-submitted_at").first()
    qr_data_uri = generate_upi_qr_data_uri(note=f"VeriScanAI-{user.id}") if not pending_request else None

    return render(request, "billing/pay.html", {
        "user": user,
        "next_url": next_url,
        "price_inr": settings.PAID_ACCESS_PRICE_INR,
        "access_days": settings.PAID_ACCESS_DAYS,
        "upi_id": settings.UPI_ID,
        "upi_configured": bool(settings.UPI_ID),
        "qr_data_uri": qr_data_uri,
        "pending_request": pending_request,
    })


@login_required
def payment_history(request):
    requests_qs = PaymentRequest.objects.filter(user=request.user).order_by("-submitted_at")
    return render(request, "billing/history.html", {
        "user": request.user, "payment_requests": requests_qs, "active_nav": "billing",
    })
