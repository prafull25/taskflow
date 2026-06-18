from django.db.models import Count, Max, Q, QuerySet
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from django_filters.rest_framework import DjangoFilterBackend

from .filters import TaskFilter
from .models import Project, Task
from .pagination import TaskFlowPagination
from .serializers import ProjectSerializer, ProjectSummarySerializer, TaskSerializer


class ProjectViewSet(ModelViewSet):
    """
    CRUD operations for Projects plus the /summary/ aggregation action.

    GET    /api/projects/
    POST   /api/projects/
    GET    /api/projects/{id}/
    PUT    /api/projects/{id}/
    PATCH  /api/projects/{id}/
    DELETE /api/projects/{id}/
    GET    /api/projects/{id}/summary/
    """

    serializer_class = ProjectSerializer
    pagination_class = TaskFlowPagination
    filter_backends: list = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields: list[str] = ["status"]
    search_fields: list[str] = ["name"]                        # hits db_index on name
    ordering_fields: list[str] = ["name", "created_at", "status"]
    ordering: list[str] = ["-created_at"]                      # deterministic default

    def get_queryset(self) -> QuerySet[Project]:
        # Single SQL execution block — one LEFT OUTER JOIN + GROUP BY produces
        # both aggregates with zero extra round-trips.
        #
        # prefetch_related("tasks") was intentionally removed: it fired a second
        # SELECT … WHERE project_id IN (…) query to hydrate full Task objects
        # that the serializer never accessed.  The annotation already joins the
        # task table, so the prefetch was pure overhead.
        #
        # Equivalent PostgreSQL statement (for EXPLAIN / index audit):
        #
        #   SELECT
        #       p.id,
        #       p.name,
        #       p.description,
        #       p.status,
        #       p.created_at,
        #       p.updated_at,
        #       COUNT(t.id)        AS task_count,
        #       MAX(t.due_date)    AS latest_due_date
        #   FROM projects_project AS p
        #   LEFT OUTER JOIN projects_task AS t
        #       ON p.id = t.project_id
        #   GROUP BY
        #       p.id          -- PK functional dependency; PostgreSQL infers the rest
        #   ORDER BY
        #       p.created_at DESC;
        #
        # Index usage expected by the planner:
        #   • projects_project: PK index (projects_project_pkey) for GROUP BY key
        #   • projects_task: FK index (projects_task_project_id_…) for the JOIN
        #   • projects_project: projects_project_status_created_idx for ORDER BY
        return (
            Project.objects.annotate(
                task_count=Count("tasks"),
                latest_due_date=Max("tasks__due_date"),
            )
            .order_by("-created_at")
        )

    # ── /api/projects/{id}/summary/ ────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request: Request, pk: int | None = None) -> Response:
        """
        Single-query aggregation: returns project name, total tasks,
        completed tasks, open tasks, and completion rate.

        The annotated queryset merges the project row with both COUNT
        expressions in one SQL statement — no N+1, no Python-side counting.
        """
        project: Project = get_object_or_404(
            Project.objects.annotate(
                total_tasks=Count("tasks"),
                completed_tasks=Count("tasks", filter=Q(tasks__is_complete=True)),
            ),
            pk=pk,
        )
        self.check_object_permissions(request, project)
        serializer = ProjectSummarySerializer(project)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TaskViewSet(ModelViewSet):
    """
    CRUD operations for Tasks with multi-field index-backed filtering.

    GET    /api/tasks/
    POST   /api/tasks/
    GET    /api/tasks/{id}/
    PUT    /api/tasks/{id}/
    PATCH  /api/tasks/{id}/
    DELETE /api/tasks/{id}/

    Filter params: ?project=<id>  ?priority=<1-4>  ?is_complete=<true|false>
                   ?assignee=<str>  ?due_date__gte=YYYY-MM-DD  ?due_date__lte=YYYY-MM-DD
                   ?priority__in=1,3
    """

    serializer_class = TaskSerializer
    pagination_class = TaskFlowPagination
    filter_backends: list = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = TaskFilter                               # declarative FilterSet
    search_fields: list[str] = ["title", "assignee", "project__name"]
    ordering_fields: list[str] = ["priority", "due_date", "is_complete"]
    ordering: list[str] = ["due_date", "-priority"]           # mirrors Task.Meta.ordering

    def get_queryset(self) -> QuerySet[Task]:
        # select_related("project") emits a single SQL JOIN rather than the N+1
        # pattern that accessing task.project.name would otherwise cause:
        #
        #   SELECT t.*, p.id, p.name, …
        #   FROM   projects_task AS t
        #   INNER JOIN projects_project AS p ON p.id = t.project_id
        #   ORDER BY t.due_date ASC NULLS LAST, t.priority DESC, t.id ASC;
        #
        # Why JOIN beats prefetch_related for this forward FK:
        #   • select_related  → 1 query; DB optimizer uses the FK index on
        #     projects_task.project_id for a hash/nested-loop join; result set
        #     stays at exactly N rows (one per task).
        #   • prefetch_related → 2 queries; the second SELECT … WHERE id IN (…)
        #     ships a potentially large IN-list over the wire, then Django stitches
        #     the two result sets in application memory.  For a *forward* FK where
        #     each task references exactly one project, the JOIN is always cheaper.
        #     prefetch_related is the right choice only for *reverse* or M2M
        #     relations where a JOIN would produce row duplication (fan-out).
        return (
            Task.objects.select_related("project")
            .order_by("due_date", "-priority", "id")
        )
    
