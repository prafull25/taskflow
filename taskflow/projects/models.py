from django.db import models


class Project(models.Model):
    """A top-level container grouping related Tasks."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On Hold"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    name: models.CharField = models.CharField(
        max_length=200,
        unique=True,          # implicit unique index
        null=False,
        blank=False,
        db_index=True,        # explicit covering index for lookup queries
    )
    description: models.TextField = models.TextField(
        max_length=5000,
        null=True,
        blank=True,
    )
    status: models.CharField = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        null=False,
        blank=False,
        db_index=True,        # filtered list views query by status
    )
    created_at: models.DateTimeField = models.DateTimeField(auto_now_add=True)
    updated_at: models.DateTimeField = models.DateTimeField(auto_now=True)

    class Meta:
        ordering: list[str] = ["-created_at"]
        verbose_name: str = "Project"
        verbose_name_plural: str = "Projects"
        indexes: list[models.Index] = [
            # compound index for status + created_at — covers the default admin list
            models.Index(fields=["status", "-created_at"], name="project_status_created_idx"),
        ]
        constraints: list[models.BaseConstraint] = [
            models.CheckConstraint(
                condition=models.Q(status__in=["active", "on_hold", "completed", "archived"]),
                name="project_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Task(models.Model):
    """An atomic unit of work belonging to a Project."""

    class Priority(models.IntegerChoices):
        LOW = 1, "Low"
        MEDIUM = 2, "Medium"
        HIGH = 3, "High"
        CRITICAL = 4, "Critical"

    title: models.CharField = models.CharField(
        max_length=300,
        null=False,
        blank=False,
        db_index=True,        # searched in admin search_fields
    )
    project: models.ForeignKey = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="tasks",
        null=False,
        blank=False,
        db_index=True,        # FK lookup; Django adds this automatically, explicit for clarity
    )
    assignee: models.CharField = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        db_index=True,        # filtered / searched in admin
    )
    priority: models.IntegerField = models.IntegerField(
        choices=Priority.choices,
        default=Priority.MEDIUM,
        null=False,
        blank=False,
        db_index=True,        # list_filter in admin
    )
    due_date: models.DateField = models.DateField(
        null=True,
        blank=True,
        db_index=True,        # date-range queries and ordering
    )
    is_complete: models.BooleanField = models.BooleanField(
        default=False,
        null=False,
        blank=False,
        db_index=True,        # boolean filter: open vs closed tasks
    )

    class Meta:
        ordering: list[str] = ["due_date", "-priority"]
        verbose_name: str = "Task"
        verbose_name_plural: str = "Tasks"
        indexes: list[models.Index] = [
            # covers the most common admin query: tasks for a project, sorted by priority
            models.Index(
                fields=["project", "is_complete", "-priority"],
                name="task_proj_cmpl_pri_idx",
            ),
            # covers assignee workload queries
            models.Index(
                fields=["assignee", "is_complete"],
                name="task_assignee_complete_idx",
            ),
        ]
        constraints: list[models.BaseConstraint] = [
            models.CheckConstraint(
                condition=models.Q(priority__in=[1, 2, 3, 4]),
                name="task_priority_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"[{self.get_priority_display()}] {self.title}"
