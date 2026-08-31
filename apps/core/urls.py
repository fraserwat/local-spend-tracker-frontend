from django.urls import path

from apps.councils import views as council_views

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("", council_views.council_dashboard, name="council-picker"),
    path("council/<slug:slug>/", council_views.council_dashboard, name="council-detail"),
]
