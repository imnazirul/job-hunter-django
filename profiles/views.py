from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CandidateProfile, CVDocument
from .serializers import (
    CandidateProfileSerializer,
    CVDocumentDetailSerializer,
    CVDocumentSerializer,
    CVUploadSerializer,
)
from .tasks import DRAFT_FIELDS, process_cv


class CVListCreateView(generics.ListCreateAPIView):
    serializer_class = CVDocumentSerializer

    def get_queryset(self):
        return CVDocument.objects.filter(user=self.request.user)

    @extend_schema(request=CVUploadSerializer, responses={201: CVDocumentSerializer})
    def post(self, request, *args, **kwargs):
        upload = CVUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        file = upload.validated_data["file"]

        cv = CVDocument.objects.create(
            user=request.user,
            file=file,
            original_filename=file.name[:255],
            size_bytes=file.size,
        )
        # Queued after commit would be safer, but the upload is not in an outer
        # transaction here and the task re-reads the row anyway.
        process_cv.delay(cv.pk)
        return Response(CVDocumentSerializer(cv).data, status=status.HTTP_201_CREATED)


class CVDetailView(generics.RetrieveAPIView):
    serializer_class = CVDocumentDetailSerializer

    def get_queryset(self):
        return CVDocument.objects.filter(user=self.request.user)


class ProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = CandidateProfileSerializer

    def get_object(self):
        profile, _ = CandidateProfile.objects.get_or_create(user=self.request.user)
        return profile


class ApplyDraftView(APIView):
    """Copy a parsed CV draft over the profile, on purpose and on request."""

    @extend_schema(request=None, responses={200: CandidateProfileSerializer})
    def post(self, request, pk):
        cv = generics.get_object_or_404(CVDocument.objects.filter(user=request.user), pk=pk)
        if not cv.draft:
            return Response(
                {"detail": f"this CV has no parsed draft yet (status {cv.status})"},
                status=status.HTTP_409_CONFLICT,
            )

        profile, _ = CandidateProfile.objects.get_or_create(user=request.user)
        for field in DRAFT_FIELDS:
            if field in cv.draft:
                setattr(profile, field, cv.draft[field])
        profile.source_cv = cv
        profile.reviewed = False
        profile.save()
        return Response(CandidateProfileSerializer(profile).data)
