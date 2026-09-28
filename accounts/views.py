from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, logout as auth_logout, authenticate
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import SignupForm, LoginForm, OTPForm, ForgotPasswordForm, ResetPasswordForm
from .models import OTP
from .utils import send_otp_email

User = get_user_model()


def landing(request):
    if request.user.is_authenticated:
        if request.user.is_admin:
            return redirect("adminpanel:dashboard")
        return redirect("detection:dashboard")

    signup_form = SignupForm()
    login_form = LoginForm()
    active_tab = request.GET.get("tab", "login")
    return render(request, "accounts/landing.html", {
        "signup_form": signup_form,
        "login_form": login_form,
        "active_tab": active_tab,
    })


def _issue_and_send_otp(email, purpose):
    otp = OTP.issue(email, purpose, expiry_minutes=settings.OTP_EXPIRY_MINUTES)
    delivered = send_otp_email(email, otp.code, purpose=purpose)
    return otp, delivered


@require_http_methods(["POST"])
def signup(request):
    form = SignupForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, err)
        return redirect(f"{reverse('accounts:landing')}?tab=signup")

    data = form.cleaned_data
    existing_unverified = User.objects.filter(email=data["email"], is_verified=False).first()

    if existing_unverified:
        existing_unverified.name = data["name"]
        existing_unverified.set_password(data["password"])
        existing_unverified.save()
    else:
        User.objects.create_user(
            email=data["email"], name=data["name"], password=data["password"],
            role="user", is_verified=False,
        )

    otp, delivered = _issue_and_send_otp(data["email"], "signup")

    request.session["pending_email"] = data["email"]
    request.session["pending_purpose"] = "signup"
    request.session["otp_delivered_by_email"] = delivered

    messages.success(request, "Account created! Enter the verification code to continue.")
    return redirect("accounts:verify_otp")


def verify_otp(request):
    email = request.session.get("pending_email")
    purpose = request.session.get("pending_purpose")

    if not email or not purpose:
        messages.error(request, "No pending verification. Please sign up or log in again.")
        return redirect("accounts:landing")

    dev_otp = None
    if not settings.EMAIL_CONFIGURED:
        latest = OTP.objects.filter(email=email, purpose=purpose, used=False).order_by("-id").first()
        if latest:
            dev_otp = latest.code

    if request.method == "GET":
        return render(request, "accounts/verify_otp.html", {
            "email": email, "purpose": purpose, "dev_otp": dev_otp,
            "email_configured": settings.EMAIL_CONFIGURED,
        })

    entered = request.POST.get("code", "").strip()

    otp = OTP.objects.filter(email=email, purpose=purpose, used=False).order_by("-id").first()

    if not otp:
        messages.error(request, "No active code found. Please request a new one.")
        return redirect("accounts:verify_otp")

    if timezone.now() > otp.expires_at:
        messages.error(request, "This code has expired. Please request a new one.")
        return redirect("accounts:verify_otp")

    if entered != otp.code:
        messages.error(request, "Incorrect code. Please try again.")
        return redirect("accounts:verify_otp")

    otp.used = True
    otp.save()

    if purpose == "signup":
        User.objects.filter(email=email).update(is_verified=True)
        request.session["scan_face_email"] = email
        request.session.pop("pending_email", None)
        request.session.pop("pending_purpose", None)
        messages.success(request, "Email verified! Please complete quick face biometric registration to finish account setup.")
        return redirect("accounts:scan_face")

    elif purpose == "reset":
        request.session["reset_email"] = email
        request.session.pop("pending_email", None)
        request.session.pop("pending_purpose", None)
        return redirect("accounts:reset_password")

    return redirect("accounts:landing")


def scan_face_view(request):
    import json
    from .face_utils import find_matching_face_user

    email = request.session.get("scan_face_email")
    if not email:
        messages.error(request, "No pending face scan session found. Please log in.")
        return redirect(f"{reverse('accounts:landing')}?tab=login")

    user = User.objects.filter(email=email, is_verified=True).first()
    if not user:
        messages.error(request, "Account not found.")
        return redirect("accounts:landing")

    if request.method == "GET":
        return render(request, "accounts/scan_face.html", {"user": user, "email": email})

    descriptor_str = request.POST.get("face_descriptor", "").strip()
    if not descriptor_str:
        messages.error(request, "Face scan failed or no face detected. Please try again.")
        return redirect("accounts:scan_face")

    try:
        candidate_vector = json.loads(descriptor_str)
    except Exception:
        candidate_vector = None

    if not candidate_vector or not isinstance(candidate_vector, list):
        messages.error(request, "Invalid facial descriptor. Please capture your face again.")
        return redirect("accounts:scan_face")

    # Perform biometric face matching across all existing registered users
    matching_user, min_dist = find_matching_face_user(candidate_vector, threshold=3.50, current_email=email)

    from adminpanel.utils import log_activity

    if matching_user:
        # Delete unverified user account to block duplicate creation
        masked_email = matching_user.email[:2] + "***@" + matching_user.email.split("@")[1]
        log_activity(
            request,
            user=user,
            user_email=email,
            action="face_rejected",
            description=f"Face registration blocked: matches existing account '{masked_email}' (distance: {min_dist:.2f})"
        )
        user.delete()
        request.session.pop("scan_face_email", None)

        messages.error(
            request,
            f"🚫 Registration Rejected! This face is already registered under existing account '{masked_email}'. "
            f"Multiple account creation with the same face is not allowed. Please log in with your registered account."
        )
        return redirect(f"{reverse('accounts:landing')}?tab=login")
    else:
        user.face_descriptor = json.dumps(candidate_vector)
        user.face_registered = True
        user.save()

        auth_login(request, user, backend="accounts.backends.EmailBackend")
        request.session.pop("scan_face_email", None)

        from .utils import send_signup_success_email
        send_signup_success_email(user.email, user.name)

        log_activity(
            request,
            user=user,
            action="face_verified",
            description="Facial biometric vector registered and verified successfully during signup."
        )

        messages.success(request, "🎉 Face registration complete! Welcome to VeriScan AI.")
        return redirect("detection:dashboard")





@require_http_methods(["POST"])
def resend_otp(request):
    email = request.session.get("pending_email")
    purpose = request.session.get("pending_purpose")
    if not email or not purpose:
        messages.error(request, "No pending verification.")
        return redirect("accounts:landing")

    _issue_and_send_otp(email, purpose)
    messages.success(request, "A new code has been sent.")
    return redirect("accounts:verify_otp")


@require_http_methods(["POST"])
def login_view(request):
    from adminpanel.utils import log_activity
    form = LoginForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid email and password.")
        return redirect(f"{reverse('accounts:landing')}?tab=login")

    email = form.cleaned_data["email"].lower().strip()
    password = form.cleaned_data["password"]

    user = authenticate(request, username=email, password=password)

    if user is None:
        log_activity(
            request,
            user_email=email,
            action="login_failed",
            description="Failed login attempt: incorrect email or password."
        )
        messages.error(request, "Invalid email or password.")
        return redirect(f"{reverse('accounts:landing')}?tab=login")

    if not user.is_active:
        log_activity(
            request,
            user=user,
            action="login_failed",
            description="Failed login attempt: user account is disabled by admin."
        )
        messages.error(request, "This account has been disabled. Contact the administrator.")
        return redirect(f"{reverse('accounts:landing')}?tab=login")

    if not user.is_verified:
        _issue_and_send_otp(email, "signup")
        request.session["pending_email"] = email
        request.session["pending_purpose"] = "signup"
        messages.error(request, "Please verify your email first. We've sent you a new code.")
        return redirect("accounts:verify_otp")

    auth_login(request, user, backend="accounts.backends.EmailBackend")

    log_activity(
        request,
        user=user,
        action="login_success",
        description=f"User logged in via Email/Password credentials ({'Admin' if user.is_admin else 'User'})."
    )

    if user.is_admin:
        return redirect("adminpanel:dashboard")
    return redirect("detection:dashboard")


@require_http_methods(["POST"])
def face_login_view(request):
    import json
    from .face_utils import find_matching_face_user
    from adminpanel.utils import log_activity

    descriptor_str = request.POST.get("face_descriptor", "").strip()
    password = request.POST.get("password", "")

    if not descriptor_str or not password:
        messages.error(request, "Please capture your face and enter your password.")
        return redirect(f"{reverse('accounts:landing')}?tab=facelogin")

    try:
        candidate_vector = json.loads(descriptor_str)
    except Exception:
        candidate_vector = None

    if not candidate_vector or not isinstance(candidate_vector, list):
        messages.error(request, "Invalid face capture. Please scan your face again.")
        return redirect(f"{reverse('accounts:landing')}?tab=facelogin")

    # Search database for user matching this face biometric vector
    matching_user, min_dist = find_matching_face_user(candidate_vector, threshold=3.50)

    if not matching_user:
        log_activity(
            request,
            action="login_failed",
            description=f"Face Login failed: No registered face matched candidate biometric vector (min distance {min_dist:.2f})."
        )
        messages.error(request, "Face not recognized! No account registered with this face.")
        return redirect(f"{reverse('accounts:landing')}?tab=facelogin")

    # Authenticate user password
    user = authenticate(request, username=matching_user.email, password=password)
    if user is None:
        log_activity(
            request,
            user=matching_user,
            action="login_failed",
            description=f"Face Login failed: Recognized face for '{matching_user.email}' but password was incorrect."
        )
        messages.error(request, f"Incorrect password for account '{matching_user.email}'.")
        return redirect(f"{reverse('accounts:landing')}?tab=facelogin")

    if not user.is_active:
        log_activity(
            request,
            user=user,
            action="login_failed",
            description="Face Login failed: Account is disabled."
        )
        messages.error(request, "This account has been disabled.")
        return redirect(f"{reverse('accounts:landing')}?tab=facelogin")

    auth_login(request, user, backend="accounts.backends.EmailBackend")
    log_activity(
        request,
        user=user,
        action="login_success",
        description=f"User logged in via Face Biometric Scan + Password (distance: {min_dist:.2f})."
    )

    messages.success(request, f"🎉 Face authenticated! Welcome back, {user.name}.")

    if user.is_admin:
        return redirect("adminpanel:dashboard")
    return redirect("detection:dashboard")



def logout_view(request):
    from adminpanel.utils import log_activity
    if request.user.is_authenticated:
        log_activity(
            request,
            user=request.user,
            action="logout",
            description="User logged out of system session."
        )
    auth_logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("accounts:landing")



def forgot_password(request):
    if request.method == "GET":
        return render(request, "accounts/forgot_password.html", {"form": ForgotPasswordForm()})

    form = ForgotPasswordForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please enter a valid email address.")
        return redirect("accounts:forgot_password")

    email = form.cleaned_data["email"].lower().strip()
    user = User.objects.filter(email=email).first()

    if user:
        _issue_and_send_otp(email, "reset")
        request.session["pending_email"] = email
        request.session["pending_purpose"] = "reset"

    messages.success(request, "If that email is registered, a reset code has been sent.")
    if user:
        return redirect("accounts:verify_otp")
    return redirect("accounts:forgot_password")


def reset_password(request):
    email = request.session.get("reset_email")
    if not email:
        messages.error(request, "Please request a password reset first.")
        return redirect("accounts:forgot_password")

    if request.method == "GET":
        return render(request, "accounts/reset_password.html", {"email": email, "form": ResetPasswordForm()})

    form = ResetPasswordForm(request.POST)
    if not form.is_valid():
        for field, errors in form.errors.items():
            for err in errors:
                messages.error(request, err)
        return redirect("accounts:reset_password")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, "Something went wrong. Please try again.")
        return redirect("accounts:forgot_password")

    user.set_password(form.cleaned_data["password"])
    user.save()
    request.session.pop("reset_email", None)

    messages.success(request, "Password reset successful. Please log in.")
    return redirect(f"{reverse('accounts:landing')}?tab=login")
