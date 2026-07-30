import logging

from django.db import transaction
from django.db.models import F, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from profiles.models import CandidateProfile

from .models import Job, SearchRun, SearchStatus, SourceRun
from .serializers import (
    JobDetailSerializer,
    JobListSerializer,
    SearchRunSerializer,
    SourceInfoSerializer,
)
from .sources.registry import all_sources, usable_sources
from .tasks import build_query, dispatch

logger = logging.getLogger(__name__)

def _ordering_expressions():
    # Postgres sorts NULLs first on a descending column, which would float
    # unscored jobs to the top of a score-sorted list.
    return {
        "score": [F("score").desc(nulls_last=True)],
        "posted": [F("posted_at").desc(nulls_last=True)],
        "newest": ["-created_at"],
    }


ORDERING_FIELDS = _ordering_expressions()


class SourceListView(APIView):
    @extend_schema(responses={200: SourceInfoSerializer(many=True)})
    def get(self, request):
        payload = [
            {
                "key": source.key,
                "name": source.name,
                "requires_key": source.requires_key,
                "configured": source.is_configured(),
            }
            for source in all_sources()
        ]
        return Response(SourceInfoSerializer(payload, many=True).data)


class SearchRunListCreateView(generics.ListCreateAPIView):
    serializer_class = SearchRunSerializer

    def get_queryset(self):
        return SearchRun.objects.filter(user=self.request.user).prefetch_related("sources")

    @extend_schema(request=None, responses={202: SearchRunSerializer})
    def post(self, request, *args, **kwargs):
        profile = CandidateProfile.objects.filter(user=request.user).first()
        if profile is None:
            return Response(
                {"detail": "upload a CV and confirm your profile before searching"},
                status=status.HTTP_409_CONFLICT,
            )
        if not profile.reviewed:
            return Response(
                {"detail": "confirm your parsed profile before searching"},
                status=status.HTTP_409_CONFLICT,
            )

        sources = usable_sources()
        if not sources:
            return Response(
                {"detail": "no job sources are configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        query = build_query(profile)
        with transaction.atomic():
            search_run = SearchRun.objects.create(
                user=request.user,
                query={
                    "titles": list(query.titles),
                    "locations": list(query.locations),
                    "remote_only": query.remote_only,
                    "limit": query.limit,
                },
            )
            SourceRun.objects.bulk_create(
                [SourceRun(search_run=search_run, source_key=source.key) for source in sources]
            )

        # Dispatched outside the transaction so the worker cannot read a row that
        # has not been committed yet.
        try:
            dispatch(search_run)
        except Exception as exc:
            logger.exception("failed to dispatch search %s", search_run.pk)
            SearchRun.objects.filter(pk=search_run.pk).update(
                status=SearchStatus.FAILED, error=f"could not queue the search: {exc}"
            )
            search_run.refresh_from_db()
            return Response(
                SearchRunSerializer(search_run).data,
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        search_run.refresh_from_db()
        return Response(SearchRunSerializer(search_run).data, status=status.HTTP_202_ACCEPTED)


class SearchRunDetailView(generics.RetrieveAPIView):
    serializer_class = SearchRunSerializer

    def get_queryset(self):
        return SearchRun.objects.filter(user=self.request.user).prefetch_related("sources")


@extend_schema(
    parameters=[
        OpenApiParameter("min_score", int, description="Only jobs scoring at least this"),
        OpenApiParameter("source", str, description="Filter to one source key"),
        OpenApiParameter("remote", bool, description="true for remote only, false for on-site"),
        OpenApiParameter("q", str, description="Substring match on title and company"),
        OpenApiParameter("search_run", int, description="Only jobs first seen in this run"),
        OpenApiParameter(
            "include_duplicates", bool, description="Include postings marked as duplicates"
        ),
        OpenApiParameter("ordering", str, enum=sorted(ORDERING_FIELDS), description="Sort order"),
    ]
)
class JobListView(generics.ListAPIView):
    serializer_class = JobListSerializer

    def get_queryset(self):
        params = self.request.query_params
        queryset = Job.objects.filter(user=self.request.user)

        if params.get("include_duplicates", "").lower() not in ("1", "true", "yes"):
            queryset = queryset.filter(is_duplicate=False)

        min_score = params.get("min_score")
        if min_score:
            try:
                queryset = queryset.filter(score__gte=int(min_score))
            except ValueError:
                pass

        if params.get("source"):
            queryset = queryset.filter(source=params["source"])

        remote = params.get("remote")
        if remote is not None and remote != "":
            queryset = queryset.filter(remote=remote.lower() in ("1", "true", "yes"))

        if params.get("q"):
            term = params["q"]
            queryset = queryset.filter(Q(title__icontains=term) | Q(company__icontains=term))

        if params.get("search_run"):
            try:
                queryset = queryset.filter(first_seen_run_id=int(params["search_run"]))
            except ValueError:
                pass

        ordering = ORDERING_FIELDS.get(params.get("ordering") or "score", ORDERING_FIELDS["score"])
        return queryset.order_by(*ordering, "-created_at")


class JobDetailView(generics.RetrieveAPIView):
    serializer_class = JobDetailSerializer

    def get_queryset(self):
        return Job.objects.filter(user=self.request.user)
