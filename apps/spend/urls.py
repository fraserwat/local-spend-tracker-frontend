from django.urls import path

from . import views

urlpatterns = [
    path(
        "councils/<slug:slug>/transactions/",
        views.TransactionListAPIView.as_view(),
        name="council-transactions",
    ),
]
