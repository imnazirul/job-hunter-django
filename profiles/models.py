from django.conf import settings
from django.db import models


class Seniority(models.TextChoices):
    INTERN = "intern"
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"
    PRINCIPAL = "principal"
    UNKNOWN = "unknown"


class RemotePreference(models.TextChoices):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    ANY = "any"


class CVStatus(models.TextChoices):
    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class CVDocument(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cvs")
    file = models.FileField(upload_to="cvs/%Y/%m/")
    original_filename = models.CharField(max_length=255)
    size_bytes = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=CVStatus.choices, default=CVStatus.UPLOADED)
    extracted_text = models.TextField(blank=True)
    error = models.TextField(blank=True)
    # The parsed profile before the user has confirmed it. Kept separate from
    # CandidateProfile so a second upload cannot silently overwrite corrections.
    draft = models.JSONField(null=True, blank=True)
    parsed_with = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    parsed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"


class CandidateProfile(models.Model):
    """The searchable version of the CV, after the user has corrected it.

    One per user for now. If profile-per-job-family turns out to matter, this
    becomes a ForeignKey with an is_default flag; there is no point guessing.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    source_cv = models.ForeignKey(
        CVDocument, on_delete=models.SET_NULL, null=True, blank=True, related_name="profiles"
    )

    full_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    location = models.CharField(max_length=200, blank=True)
    summary = models.TextField(blank=True)

    seniority = models.CharField(
        max_length=20, choices=Seniority.choices, default=Seniority.UNKNOWN
    )
    years_experience = models.PositiveSmallIntegerField(null=True, blank=True)
    skills = models.JSONField(default=list, blank=True)
    target_titles = models.JSONField(default=list, blank=True)
    preferred_locations = models.JSONField(default=list, blank=True)
    remote_preference = models.CharField(
        max_length=20, choices=RemotePreference.choices, default=RemotePreference.ANY
    )
    excluded_keywords = models.JSONField(default=list, blank=True)

    # Nothing searches or sends until the user has looked at the parsed draft.
    reviewed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"profile for {self.user_id}"
