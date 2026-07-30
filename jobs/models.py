from django.conf import settings
from django.db import models


class SearchStatus(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    # At least one source failed but the run produced results anyway.
    PARTIAL = "partial"
    FAILED = "failed"


class SourceStatus(models.TextChoices):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    SKIPPED = "skipped"


class ScoredBy(models.TextChoices):
    RULES = "rules"
    LLM = "llm"


class SearchRun(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_runs"
    )
    status = models.CharField(max_length=20, choices=SearchStatus.choices, default=SearchStatus.QUEUED)
    # What the profile looked like when the run started, so a later profile edit
    # does not make old results inexplicable.
    query = models.JSONField(default=dict)
    jobs_found = models.PositiveIntegerField(default=0)
    jobs_new = models.PositiveIntegerField(default=0)
    duplicates_marked = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"search {self.pk} ({self.status})"


class SourceRun(models.Model):
    search_run = models.ForeignKey(SearchRun, on_delete=models.CASCADE, related_name="sources")
    source_key = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=SourceStatus.choices, default=SourceStatus.PENDING)
    fetched = models.PositiveIntegerField(default=0)
    created = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["search_run", "source_key"], name="unique_source_per_search"
            )
        ]
        ordering = ["source_key"]

    def __str__(self):
        return f"{self.source_key} ({self.status})"


class Job(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="jobs")
    source = models.CharField(max_length=50)
    source_job_id = models.CharField(max_length=200)

    title = models.CharField(max_length=300)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True)
    remote = models.BooleanField(null=True)
    # Plain text. The HTML the boards return is stripped on the way in so that
    # nothing downstream has to think about markup or injection.
    description = models.TextField(blank=True)
    url = models.URLField(max_length=1000)
    apply_url = models.URLField(max_length=1000, blank=True)
    salary_text = models.CharField(max_length=200, blank=True)
    tags = models.JSONField(default=list, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    fingerprint = models.CharField(max_length=64, db_index=True)
    is_duplicate = models.BooleanField(default=False)
    duplicate_of = models.ForeignKey(
        "self", on_delete=models.SET_NULL, null=True, blank=True, related_name="duplicates"
    )

    score = models.PositiveSmallIntegerField(null=True, blank=True)
    score_reasons = models.JSONField(default=list, blank=True)
    missing_skills = models.JSONField(default=list, blank=True)
    scored_by = models.CharField(max_length=10, choices=ScoredBy.choices, blank=True)
    scored_at = models.DateTimeField(null=True, blank=True)

    first_seen_run = models.ForeignKey(
        SearchRun, on_delete=models.SET_NULL, null=True, blank=True, related_name="jobs"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "source", "source_job_id"], name="unique_job_per_user_source"
            )
        ]
        indexes = [
            models.Index(fields=["user", "-score"]),
            models.Index(fields=["user", "is_duplicate"]),
        ]
        ordering = ["-score", "-posted_at"]

    def __str__(self):
        return f"{self.title} at {self.company}"
