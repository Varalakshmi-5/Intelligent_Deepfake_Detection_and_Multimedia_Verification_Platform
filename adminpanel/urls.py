from django.urls import path
from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("users/", views.manage_users, name="manage_users"),
    path("users/<int:user_id>/toggle-active/", views.toggle_user_active, name="toggle_user_active"),
    path("users/<int:user_id>/grant-access/", views.grant_access, name="grant_access"),
    path("users/<int:user_id>/delete/", views.delete_user, name="delete_user"),
    path("detections/", views.all_detections, name="all_detections"),
    path("detections/<int:detection_id>/download/", views.download_report, name="download_report"),
    path("payment-requests/", views.payment_requests, name="payment_requests"),
    path("payment-requests/<int:request_id>/approve/", views.approve_payment_request, name="approve_payment_request"),
    path("payment-requests/<int:request_id>/reject/", views.reject_payment_request, name="reject_payment_request"),
    path("feedbacks/", views.all_feedbacks, name="all_feedbacks"),
    path("feedbacks/<int:feedback_id>/toggle-reviewed/", views.toggle_feedback_reviewed, name="toggle_feedback_reviewed"),
    path("feedbacks/<int:feedback_id>/add-notes/", views.add_feedback_notes, name="add_feedback_notes"),
    path("feedbacks/<int:feedback_id>/delete/", views.delete_feedback, name="delete_feedback"),
    path("settings/", views.admin_settings, name="settings"),
    path("audit-logs/", views.audit_logs, name="audit_logs"),
    path("audit-logs/export-csv/", views.export_audit_logs_csv, name="export_audit_logs_csv"),
]

