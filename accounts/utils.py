from django.conf import settings
from django.core.mail import send_mail


def send_otp_email(email, code, purpose="signup"):
    """
    Sends the OTP via Django's email backend if SMTP is configured.
    Otherwise (DEV MODE), prints it to the console so the app works
    with zero email setup. The OTP is also always shown on-screen
    in the UI regardless of delivery method.
    """
    subject = "Your verification code" if purpose == "signup" else "Your password reset code"
    message = (
        f"Your one-time verification code is: {code}\n\n"
        f"This code expires in {settings.OTP_EXPIRY_MINUTES} minutes.\n"
        f"If you did not request this, you can safely ignore this email."
    )

    if not settings.EMAIL_CONFIGURED:
        print("=" * 50)
        print(f"[DEV MODE - NO SMTP CONFIGURED] OTP for {email} ({purpose}): {code}")
        print("=" * 50)
        return False

    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL, [email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        print(f"[EMAIL SEND FAILED] Falling back to on-screen OTP. Reason: {exc}")
        print(f"[DEV MODE] OTP for {email} ({purpose}): {code}")
        return False


def send_signup_success_email(email, name):
    """
    Sends a welcome/signup completion notification email.
    """
    subject = "Welcome to VeriScan AI - Signup Completed Successfully!"
    message = (
        f"Hello {name or 'User'},\n\n"
        f"Congratulations! Your registration with VeriScan AI has been successfully completed.\n"
        f"Your face biometric profile has been verified and registered.\n\n"
        f"You can now log in to access all features.\n\n"
        f"Best regards,\n"
        f"VeriScan AI Team"
    )

    if not settings.EMAIL_CONFIGURED:
        print("=" * 50)
        print(f"[DEV MODE - NO SMTP CONFIGURED] Signup Success Email to {email}")
        print("=" * 50)
        return False

    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL, [email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        print(f"[EMAIL SEND FAILED] Signup success email to {email} failed. Reason: {exc}")
        return False


def send_payment_approval_email(email, name, days_granted=None):
    """
    Sends a notification email when a payment request / access grant is approved by admin.
    """
    days_info = f" {days_granted} days of" if days_granted else ""
    subject = "VeriScan AI - Payment Request Approved!"
    message = (
        f"Hello {name or 'User'},\n\n"
        f"Great news! Your payment request has been approved by the admin.\n"
        f"You have been granted{days_info} full access to VeriScan AI services.\n\n"
        f"Log in to your account now to start using the platform.\n\n"
        f"Best regards,\n"
        f"VeriScan AI Team"
    )

    if not settings.EMAIL_CONFIGURED:
        print("=" * 50)
        print(f"[DEV MODE - NO SMTP CONFIGURED] Payment Approval Email to {email}")
        print("=" * 50)
        return False

    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL, [email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        print(f"[EMAIL SEND FAILED] Payment approval email to {email} failed. Reason: {exc}")
        return False


def send_feedback_acknowledgement_email(email, name, subject_text, rating):
    """
    Sends a confirmation email thanking the user for submitting feedback.
    """
    subject = "Thank you for your feedback! - VeriScan AI"
    message = (
        f"Hello {name or 'User'},\n\n"
        f"Thank you for submitting your feedback on '{subject_text}' with a rating of {rating}/5 stars.\n\n"
        f"We appreciate your valuable input as it helps us continuously improve VeriScan AI.\n"
        f"Our team has received your submission and will review it shortly.\n\n"
        f"Best regards,\n"
        f"VeriScan AI Team"
    )

    if not settings.EMAIL_CONFIGURED:
        print("=" * 50)
        print(f"[DEV MODE - NO SMTP CONFIGURED] Feedback Thank You Email to {email}")
        print("=" * 50)
        return False

    try:
        send_mail(
            subject, message, settings.DEFAULT_FROM_EMAIL, [email],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        print(f"[EMAIL SEND FAILED] Feedback acknowledgement email to {email} failed. Reason: {exc}")
        return False


