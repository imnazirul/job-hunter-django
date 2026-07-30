import logging

from celery import shared_task
from django.utils import timezone

from .cv_text import CVExtractionError, extract_text
from .models import CVDocument, CVStatus, CandidateProfile
from .parsing import parse_profile

logger = logging.getLogger(__name__)

DRAFT_FIELDS = (
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
)


@shared_task
def process_cv(cv_id):
    """Extract text, then build a profile draft.

    A CV we cannot read is a user-fixable problem, so it is recorded on the row
    and the task ends quietly. Anything else (a missing row, a broken database)
    is a bug and is allowed to fail the task loudly.
    """
    cv = CVDocument.objects.get(pk=cv_id)

    CVDocument.objects.filter(pk=cv.pk).update(status=CVStatus.EXTRACTING, error="")
    try:
        with cv.file.open("rb") as handle:
            text = extract_text(handle, cv.original_filename)
    except CVExtractionError as exc:
        logger.info("CV %s rejected: %s", cv.pk, exc)
        CVDocument.objects.filter(pk=cv.pk).update(status=CVStatus.FAILED, error=str(exc))
        return {"cv_id": cv_id, "status": CVStatus.FAILED}
    except FileNotFoundError as exc:
        CVDocument.objects.filter(pk=cv.pk).update(
            status=CVStatus.FAILED, error=f"the uploaded file is missing from storage: {exc}"
        )
        return {"cv_id": cv_id, "status": CVStatus.FAILED}

    cv.extracted_text = text
    cv.status = CVStatus.PARSING
    cv.save(update_fields=["extracted_text", "status"])

    draft, parsed_with = parse_profile(text)

    cv.draft = draft
    cv.parsed_with = parsed_with
    cv.status = CVStatus.PARSED
    cv.parsed_at = timezone.now()
    cv.save(update_fields=["draft", "parsed_with", "status", "parsed_at"])

    _seed_profile_if_empty(cv, draft)
    return {"cv_id": cv_id, "status": CVStatus.PARSED, "parsed_with": parsed_with}


def _seed_profile_if_empty(cv, draft):
    """Populate the profile on a first upload only.

    Once the user has reviewed their profile, a new CV produces a draft they can
    accept explicitly. Overwriting reviewed data behind their back is the kind of
    thing that makes people stop trusting the app.
    """
    profile, created = CandidateProfile.objects.get_or_create(user=cv.user)
    if not created and profile.reviewed:
        return

    for field in DRAFT_FIELDS:
        value = draft.get(field)
        if value is None and field != "years_experience":
            continue
        setattr(profile, field, value)
    profile.source_cv = cv
    profile.reviewed = False
    profile.save()
