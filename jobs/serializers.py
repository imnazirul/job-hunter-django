from rest_framework import serializers

from .models import Job, SearchRun, SourceRun


class SourceRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceRun
        fields = ["source_key", "status", "fetched", "created", "error", "started_at", "finished_at"]
        read_only_fields = fields


class SearchRunSerializer(serializers.ModelSerializer):
    sources = SourceRunSerializer(many=True, read_only=True)

    class Meta:
        model = SearchRun
        fields = [
            "id",
            "status",
            "query",
            "jobs_found",
            "jobs_new",
            "duplicates_marked",
            "error",
            "sources",
            "created_at",
            "started_at",
            "finished_at",
        ]
        read_only_fields = fields


class JobListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Job
        fields = [
            "id",
            "source",
            "title",
            "company",
            "location",
            "remote",
            "url",
            "apply_url",
            "salary_text",
            "tags",
            "posted_at",
            "score",
            "scored_by",
            "missing_skills",
            "created_at",
        ]
        read_only_fields = fields


class JobDetailSerializer(serializers.ModelSerializer):
    duplicate_count = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = JobListSerializer.Meta.fields + [
            "description",
            "score_reasons",
            "scored_at",
            "is_duplicate",
            "duplicate_of",
            "duplicate_count",
            "first_seen_run",
        ]
        read_only_fields = fields

    def get_duplicate_count(self, job) -> int:
        return job.duplicates.count()


class SourceInfoSerializer(serializers.Serializer):
    key = serializers.CharField()
    name = serializers.CharField()
    requires_key = serializers.BooleanField()
    configured = serializers.BooleanField()
