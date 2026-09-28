from django.urls import path
from . import views

app_name = "detection"

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("analyze/image/", views.analyze_image, name="analyze_image"),
    path("analyze/video/", views.analyze_video, name="analyze_video"),
    path("analyze/audio/", views.analyze_audio, name="analyze_audio"),
    path("analyze/text/", views.analyze_text, name="analyze_text"),
    path("analyze/document/", views.analyze_document, name="analyze_document"),
    path("analyze/link/", views.analyze_link, name="analyze_link"),
    path("compare/", views.compare_files_view, name="compare_files"),
    path("proctor/", views.analyze_proctoring, name="analyze_proctoring"),
    path("history/", views.history, name="history"),

    path("report/<int:detection_id>/download/", views.download_report, name="download_report"),
    path("certificate/<int:detection_id>/download/", views.download_certificate, name="download_certificate"),
    path("verify/<uuid:public_id>/", views.verify_certificate, name="verify_certificate"),

    path("agent/", views.agentic_assistant, name="agentic_assistant"),
    path("agent/chat/", views.agentic_chat_api, name="agentic_chat_api"),
    path("analyze/batch/", views.batch_analyze, name="batch_analyze"),
    path("crawler/", views.web_crawler, name="web_crawler"),
    path("jobs/", views.job_verifier, name="job_verifier"),
    path("recruiter/", views.recruiter_verifier, name="recruiter_verifier"),
    path("analytics/", views.threat_analytics, name="threat_analytics"),
]




