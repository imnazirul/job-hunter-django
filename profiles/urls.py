from django.urls import path

from .views import ApplyDraftView, CVDetailView, CVListCreateView, ProfileView

urlpatterns = [
    path("cvs/", CVListCreateView.as_view(), name="cv-list"),
    path("cvs/<int:pk>/", CVDetailView.as_view(), name="cv-detail"),
    path("cvs/<int:pk>/apply-draft/", ApplyDraftView.as_view(), name="cv-apply-draft"),
    path("profile/", ProfileView.as_view(), name="profile"),
]
