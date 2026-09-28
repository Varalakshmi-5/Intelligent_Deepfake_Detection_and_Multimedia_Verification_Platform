from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.login_view, name="login"),
    path("face-login/", views.face_login_view, name="face_login"),
    path("logout/", views.logout_view, name="logout"),

    path("verify-otp/", views.verify_otp, name="verify_otp"),
    path("scan-face/", views.scan_face_view, name="scan_face"),
    path("resend-otp/", views.resend_otp, name="resend_otp"),

    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/", views.reset_password, name="reset_password"),
]
