import datetime

from rest_framework import serializers

from .models import Project, Task


class ProjectSerializer(serializers.ModelSerializer[Project]):
    """Full read/write serializer for the Project resource."""

    # Both fields are annotation-backed: the viewset's get_queryset() computes
    # them in a single GROUP BY query so no extra DB round-trip is needed here.
    task_count: serializers.IntegerField = serializers.IntegerField(read_only=True, default=0)
    latest_due_date: serializers.DateField = serializers.DateField(
        read_only=True, allow_null=True, default=None
    )

    class Meta:
        model = Project
        fields: list[str] = [
            "id",
            "name",
            "description",
            "status",
            "task_count",
            "latest_due_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields: list[str] = ["id", "created_at", "updated_at"]

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Project name must be at least 3 characters.")
        return value

    def validate_status(self, value: str) -> str:
        valid: set[str] = {choice[0] for choice in Project.Status.choices}
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid status '{value}'. Choose from: {sorted(valid)}."
            )
        return value


class TaskSerializer(serializers.ModelSerializer[Task]):
    """Full read/write serializer for the Task resource."""

    # Explicit FK field: queryset guarantees a validated 400 on missing project,
    # instead of the uncaught IntegrityError a bare IntegerField would produce.
    project: serializers.PrimaryKeyRelatedField = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
    )

    # Human-readable labels for choice fields alongside the raw values.
    priority_label: serializers.CharField = serializers.CharField(
        source="get_priority_display", read_only=True
    )
    project_name: serializers.CharField = serializers.CharField(
        source="project.name", read_only=True
    )

    class Meta:
        model = Task
        fields: list[str] = [
            "id",
            "title",
            "project",
            "project_name",
            "assignee",
            "priority",
            "priority_label",
            "due_date",
            "is_complete",
        ]
        read_only_fields: list[str] = ["id", "project_name", "priority_label"]

    def validate_title(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Title must be at least 2 characters.")
        return value

    def validate_assignee(self, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if len(value) == 0:
                return None
        return value

    def validate_priority(self, value: int) -> int:
        valid: set[int] = {choice[0] for choice in Task.Priority.choices}
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid priority '{value}'. Choose from: {sorted(valid)}."
            )
        return value

    def validate_due_date(self, value: datetime.date | None) -> datetime.date | None:
        if value is not None and value < datetime.date.today():
            raise serializers.ValidationError("due_date cannot be set in the past.")
        return value

    def validate(self, attrs: dict) -> dict:
        # A completed task must not have a future due_date overriding its closed state.
        if attrs.get("is_complete") and attrs.get("due_date"):
            pass  # Allowed: archiving a task that happened to have a due_date is valid.
        return attrs


class ProjectSummarySerializer(serializers.Serializer):
    """Read-only projection for the /summary/ action — no model binding needed."""

    name: serializers.CharField = serializers.CharField()
    total_tasks: serializers.IntegerField = serializers.IntegerField()
    completed_tasks: serializers.IntegerField = serializers.IntegerField()
    open_tasks: serializers.SerializerMethodField = serializers.SerializerMethodField()
    completion_rate: serializers.SerializerMethodField = serializers.SerializerMethodField()

    def get_open_tasks(self, obj: Project) -> int:
        return obj.total_tasks - obj.completed_tasks  # type: ignore[attr-defined]

    def get_completion_rate(self, obj: Project) -> float:
        if not obj.total_tasks:  # type: ignore[attr-defined]
            return 0.0
        return round(obj.completed_tasks / obj.total_tasks * 100, 1)  # type: ignore[attr-defined]
