from django.urls import path
from . import views

app_name = "support"

urlpatterns = [
    path("", views.my_thread, name="my_thread"),
    path("poll/", views.my_thread_poll, name="my_thread_poll"),
    path("feedback/", views.user_feedback, name="feedback"),
    path("admin/", views.admin_thread_list, name="admin_thread_list"),
    path("admin/<int:user_id>/", views.admin_thread_detail, name="admin_thread_detail"),
    path("admin/<int:user_id>/poll/", views.admin_thread_poll, name="admin_thread_poll"),
]

