from django.urls import path

from apps.councils import views as council_views
from apps.spend import views as spend_views

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("", council_views.council_dashboard, name="council-picker"),
    path("council/<slug:slug>/", council_views.council_dashboard, name="council-detail"),
    path("council/<slug:slug>/spend/", spend_views.council_spend_view, name="council-spend"),
]
