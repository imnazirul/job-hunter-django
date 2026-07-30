from django.urls import path

from .views import (
    JobDetailView,
    JobListView,
    SearchRunDetailView,
    SearchRunListCreateView,
    SourceListView,
)

urlpatterns = [
    path("jobs/", JobListView.as_view(), name="job-list"),
    path("jobs/<int:pk>/", JobDetailView.as_view(), name="job-detail"),
    path("searches/", SearchRunListCreateView.as_view(), name="search-list"),
    path("searches/<int:pk>/", SearchRunDetailView.as_view(), name="search-detail"),
    path("sources/", SourceListView.as_view(), name="source-list"),
]
