from django.urls import path

from apps.councils.views import MapView

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("", MapView.as_view(), name="map"),
]
