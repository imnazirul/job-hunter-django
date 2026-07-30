from django.conf import settings
from rest_framework import serializers

from .models import CandidateProfile, CVDocument

ALLOWED_CV_EXTENSIONS = {"pdf", "docx"}


def _string_list(max_items, max_length=80):
    return serializers.ListField(
        child=serializers.CharField(max_length=max_length, allow_blank=False),
        required=False,
        max_length=max_items,
    )


class CVUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, upload):
        if upload.size == 0:
            raise serializers.ValidationError("the file is empty")
        if upload.size > settings.MAX_CV_UPLOAD_BYTES:
            limit_mb = settings.MAX_CV_UPLOAD_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"the file is larger than {limit_mb} MB")

        name = upload.name or ""
        extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if extension not in ALLOWED_CV_EXTENSIONS:
            raise serializers.ValidationError("upload a PDF or DOCX file")
        return upload


class CVDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CVDocument
        fields = [
            "id",
            "original_filename",
            "size_bytes",
            "status",
            "error",
            "parsed_with",
            "draft",
            "created_at",
            "parsed_at",
        ]
        read_only_fields = fields


class CVDocumentDetailSerializer(CVDocumentSerializer):
    class Meta(CVDocumentSerializer.Meta):
        fields = CVDocumentSerializer.Meta.fields + ["extracted_text"]
        read_only_fields = fields


class CandidateProfileSerializer(serializers.ModelSerializer):
    skills = _string_list(60)
    target_titles = _string_list(12, max_length=120)
    preferred_locations = _string_list(12, max_length=120)
    excluded_keywords = _string_list(30)

    class Meta:
        model = CandidateProfile
        fields = [
            "id",
            "full_name",
            "contact_email",
            "phone",
            "location",
            "summary",
            "seniority",
            "years_experience",
            "skills",
            "target_titles",
            "preferred_locations",
            "remote_preference",
            "excluded_keywords",
            "reviewed",
            "source_cv",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "source_cv", "created_at", "updated_at"]

    def validate(self, attrs):
        merged_titles = attrs.get("target_titles", getattr(self.instance, "target_titles", []))
        reviewed = attrs.get("reviewed", getattr(self.instance, "reviewed", False))
        # A reviewed profile with no titles produces a search with nothing to query.
        if reviewed and not merged_titles:
            raise serializers.ValidationError(
                {"target_titles": "add at least one target job title before confirming"}
            )
        return attrs
