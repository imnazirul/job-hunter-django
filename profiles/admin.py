from django.contrib import admin

from .models import CandidateProfile, CVDocument


@admin.register(CVDocument)
class CVDocumentAdmin(admin.ModelAdmin):
    list_display = ["original_filename", "user", "status", "parsed_with", "created_at"]
    list_filter = ["status", "parsed_with"]
    search_fields = ["original_filename", "user__email"]


@admin.register(CandidateProfile)
class CandidateProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "seniority", "years_experience", "reviewed", "updated_at"]
    list_filter = ["seniority", "reviewed", "remote_preference"]
    search_fields = ["user__email", "full_name"]
