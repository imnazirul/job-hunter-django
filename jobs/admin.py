from django.contrib import admin

from .models import Job, SearchRun, SourceRun


class SourceRunInline(admin.TabularInline):
    model = SourceRun
    extra = 0
    readonly_fields = ["source_key", "status", "fetched", "created", "error"]


@admin.register(SearchRun)
class SearchRunAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "status", "jobs_found", "jobs_new", "created_at"]
    list_filter = ["status"]
    inlines = [SourceRunInline]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ["title", "company", "source", "score", "scored_by", "is_duplicate"]
    list_filter = ["source", "scored_by", "is_duplicate", "remote"]
    search_fields = ["title", "company", "user__email"]
