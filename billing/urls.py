from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("pay/", views.pay, name="pay"),
    path("history/", views.payment_history, name="history"),
]
