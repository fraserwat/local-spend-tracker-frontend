from django.urls import path

from . import views

urlpatterns = [
    path("councils/", views.CouncilListView.as_view(), name="council-list"),
]
