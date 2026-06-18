from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Project, Task


class TaskInline(admin.TabularInline):
    """Inline Task list shown inside the Project change page."""

    model = Task
    extra = 0
    fields = ("title", "assignee", "priority", "due_date", "is_complete")
    readonly_fields: tuple[str, ...] = ()
    show_change_link = True


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    # ── list view ──────────────────────────────────────────────────────────
    list_display: tuple[str, ...] = (
        "name",
        "status",
        "task_count",
        "created_at",
        "updated_at",
    )
    list_filter: tuple[str, ...] = ("status", "created_at")
    search_fields: tuple[str, ...] = ("name",)          # hits the db_index on name
    ordering: tuple[str, ...] = ("-created_at",)
    date_hierarchy: str = "created_at"

    # ── detail view ────────────────────────────────────────────────────────
    readonly_fields: tuple[str, ...] = ("created_at", "updated_at")
    fieldsets: tuple = (
        (None, {"fields": ("name", "status")}),
        ("Details", {"fields": ("description",)}),
        ("Timestamps", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    inlines: list = [TaskInline]

    # ── queryset optimisation ──────────────────────────────────────────────
    def get_queryset(self, request: HttpRequest) -> QuerySet[Project]:
        return (
            super()
            .get_queryset(request)
            .prefetch_related("tasks")
        )

    @admin.display(description="Tasks")
    def task_count(self, obj: Project) -> int:
        return obj.tasks.count()


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # ── list view ──────────────────────────────────────────────────────────
    list_display: tuple[str, ...] = (
        "title",
        "project",
        "assignee",
        "priority",
        "due_date",
        "is_complete",
    )
    list_filter: tuple[str, ...] = (
        "is_complete",    # hits task_project_complete_priority_idx
        "priority",       # hits db_index on priority
        "due_date",
        "project",
    )
    search_fields: tuple[str, ...] = (
        "title",          # hits db_index on title
        "assignee",       # hits db_index on assignee
        "project__name",  # hits db_index on project.name
    )
    ordering: tuple[str, ...] = ("due_date", "-priority")
    list_select_related: tuple[str, ...] = ("project",)   # avoids N+1 on project column
    date_hierarchy: str = "due_date"

    # ── detail view ────────────────────────────────────────────────────────
    fieldsets: tuple = (
        (None, {"fields": ("title", "project")}),
        ("Assignment", {"fields": ("assignee", "priority", "due_date")}),
        ("State", {"fields": ("is_complete",)}),
    )

    # ── bulk actions ───────────────────────────────────────────────────────
    actions: list[str] = ["mark_complete", "mark_incomplete"]

    @admin.action(description="Mark selected tasks as complete")
    def mark_complete(self, request: HttpRequest, queryset: QuerySet[Task]) -> None:
        queryset.update(is_complete=True)

    @admin.action(description="Mark selected tasks as incomplete")
    def mark_incomplete(self, request: HttpRequest, queryset: QuerySet[Task]) -> None:
        queryset.update(is_complete=False)
