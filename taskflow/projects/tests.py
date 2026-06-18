"""
Regression tests for the two structural defects patched in this refactor:

  1. TaskSerializer previously accepted a bare IntegerField for `project`,
     causing an unhandled 500/IntegrityError on unknown PKs.
     Fix: PrimaryKeyRelatedField(queryset=Project.objects.all()) → clean 400.

  2. TaskViewSet.get_queryset applied `priority__icontains` against a
     PostgreSQL IntegerField, raising ProgrammingError at query time.
     Fix: integer-exact lookup via TaskFilter (DjangoFilterBackend).
"""

from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import Project, Task


class TaskForeignKeyIntegrityTest(APITestCase):
    """Verifies that an invalid project FK produces a 400, not a 500."""

    TASKS_URL: str = "/api/tasks/"

    def setUp(self) -> None:
        self.client: APIClient = APIClient()
        self.project: Project = Project.objects.create(
            name="Integrity Project",
            status=Project.Status.ACTIVE,
        )

    def test_valid_project_fk_creates_task(self) -> None:
        payload: dict = {
            "title": "Valid task",
            "project": self.project.pk,
            "priority": Task.Priority.MEDIUM,
            "is_complete": False,
        }
        response = self.client.post(self.TASKS_URL, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.count(), 1)

    def test_nonexistent_project_fk_returns_400(self) -> None:
        """
        Regression: bare IntegerField allowed any integer through, deferring
        the failure to the DB layer as a 500.  PrimaryKeyRelatedField must
        reject unknown PKs at serializer validation time with HTTP 400.
        """
        payload: dict = {
            "title": "Orphaned task",
            "project": 999_999,          # PK that will never exist
            "priority": Task.Priority.HIGH,
            "is_complete": False,
        }
        response = self.client.post(self.TASKS_URL, payload, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_400_BAD_REQUEST,
            msg="Expected 400 from PrimaryKeyRelatedField validation; got a server error instead.",
        )
        self.assertIn(
            "project",
            response.data,
            msg="Error detail must name the offending field so clients can action it.",
        )
        self.assertEqual(Task.objects.count(), 0)


class TaskPriorityFilterTest(APITestCase):
    """Verifies that ?priority=N executes a clean integer-exact DB query."""

    TASKS_URL: str = "/api/tasks/"

    def setUp(self) -> None:
        self.client: APIClient = APIClient()
        self.project: Project = Project.objects.create(
            name="Filter Project",
            status=Project.Status.ACTIVE,
        )
        Task.objects.create(
            title="High priority task",
            project=self.project,
            priority=Task.Priority.HIGH,      # 3
            is_complete=False,
        )
        Task.objects.create(
            title="Low priority task",
            project=self.project,
            priority=Task.Priority.LOW,       # 1
            is_complete=False,
        )

    def test_priority_filter_returns_200_without_db_error(self) -> None:
        """
        Regression: `priority__icontains` against an IntegerField raises
        ProgrammingError in PostgreSQL.  The fix delegates to TaskFilter which
        emits an exact integer comparison (priority = 3).
        """
        response = self.client.get(self.TASKS_URL, {"priority": Task.Priority.HIGH})

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
            msg="Priority filter must not cause a DB execution error (ProgrammingError).",
        )

    def test_priority_filter_returns_only_matching_tasks(self) -> None:
        """Ensures the exact-match filter returns only tasks of the requested priority."""
        response = self.client.get(self.TASKS_URL, {"priority": Task.Priority.HIGH})

        results: list[dict] = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "High priority task")
        self.assertEqual(results[0]["priority"], Task.Priority.HIGH)

    def test_priority_filter_excludes_other_priorities(self) -> None:
        """Sanity-check: filtering on LOW excludes the HIGH task."""
        response = self.client.get(self.TASKS_URL, {"priority": Task.Priority.LOW})

        results: list[dict] = response.data["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["priority"], Task.Priority.LOW)
