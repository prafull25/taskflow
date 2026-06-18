"""
Management command: seed_db

Populates the local PostgreSQL database with realistic test data at scale:
  • 50 distinct Project records with varied statuses and descriptions
  • 200 Task records bulk-inserted in a single batch, distributed evenly
    across all projects with varied priorities, assignees, and due dates
    spanning both historical past and future deadlines.

Usage:
    python manage.py seed_db            # append-safe; skips if data exists
    python manage.py seed_db --reset    # truncate then re-seed
"""

import itertools
import random
from datetime import date, timedelta
from typing import Final

from django.core.management.base import BaseCommand
from django.db import transaction

from projects.models import Project, Task

# ── Seed constant ─────────────────────────────────────────────────────────────
# Fixed seed guarantees identical output on every run, making the dataset
# deterministic and safe to reference in documentation or manual test steps.
_RANDOM_SEED: Final[int] = 42

# ── Target record counts ───────────────────────────────────────────────────────
_PROJECT_COUNT: Final[int] = 50
_TASK_COUNT: Final[int] = 200

# ── Corpus: Project names ──────────────────────────────────────────────────────
# 25 prefixes × 20 suffixes = 500 unique combinations; sample 50 guarantees
# that every project name satisfies the model's unique constraint.
_PROJECT_PREFIXES: Final[list[str]] = [
    "Apollo",    "Beacon",    "Cascade",   "Delta",    "Echo",
    "Falcon",    "Genesis",   "Harbor",    "Iris",     "Juno",
    "Keystone",  "Lattice",   "Meridian",  "Nexus",    "Orbit",
    "Pinnacle",  "Quantum",   "Radius",    "Solstice", "Titan",
    "Unity",     "Vector",    "Warden",    "Xenon",    "Zephyr",
]

_PROJECT_SUFFIXES: Final[list[str]] = [
    "Platform",   "Initiative", "Framework",  "System",    "Engine",
    "Hub",        "Portal",     "Suite",      "Pipeline",  "Toolkit",
    "Dashboard",  "Gateway",    "Interface",  "Module",    "Service",
    "Core",       "Cloud",      "Edge",       "Mesh",      "Relay",
]

# ── Corpus: Project descriptions ───────────────────────────────────────────────
_DESCRIPTION_TEMPLATES: Final[list[str]] = [
    (
        "Deliver a scalable {adjective} solution aligned with Q{quarter} OKRs "
        "and available team capacity."
    ),
    (
        "Cross-functional initiative to modernise the {layer} layer before the "
        "next major release cycle."
    ),
    (
        "Strategic refactor targeting latency reduction and improved observability "
        "across {layer} services."
    ),
    (
        "Foundation work enabling the {layer} team to ship features at a "
        "sustainable engineering pace."
    ),
    (
        "Customer-facing {adjective} improvement with direct impact on NPS "
        "and long-term retention metrics."
    ),
    (
        "Internal tooling upgrade to reduce operational toil and improve "
        "developer productivity across the {layer} domain."
    ),
    (
        "Compliance-driven effort to meet new data-residency requirements "
        "ahead of the Q{quarter} audit window."
    ),
    (
        "Research spike to evaluate {adjective} third-party integrations and "
        "produce a formal recommendation document."
    ),
]

_DESC_ADJECTIVES: Final[list[str]] = [
    "high-performance", "cloud-native", "event-driven",
    "fault-tolerant",   "observable",   "privacy-first",
]

_DESC_LAYERS: Final[list[str]] = [
    "data", "API", "infrastructure", "frontend",
    "authentication", "notification",
]

# ── Corpus: Task titles ────────────────────────────────────────────────────────
_TASK_VERBS: Final[list[str]] = [
    "Implement",  "Refactor",   "Design",    "Audit",      "Migrate",
    "Optimise",   "Document",   "Review",    "Deploy",     "Monitor",
    "Test",       "Integrate",  "Configure", "Analyse",    "Validate",
    "Build",      "Research",   "Prototype", "Automate",   "Debug",
]

_TASK_OBJECTS: Final[list[str]] = [
    "authentication layer",         "database schema",
    "REST endpoint contracts",      "CI/CD pipeline",
    "distributed caching strategy", "error handling middleware",
    "load balancer configuration",  "API rate-limiting policy",
    "structured logging framework", "user permission matrix",
    "data migration scripts",       "full-text search indexing",
    "async notification service",   "payment gateway integration",
    "executive reporting module",   "webhook event listeners",
    "background job queue",         "file upload service",
    "OAuth2 token refresh flow",    "admin dashboard components",
]

# ── Corpus: Assignees ──────────────────────────────────────────────────────────
_ASSIGNEES: Final[list[str]] = [
    "alice.chen",   "bob.martinez",  "carol.singh",  "dave.okonkwo",
    "eve.tanaka",   "frank.mueller", "grace.kim",    "henry.patel",
    "isla.novak",   "james.osei",
]

# ── Due-date window ────────────────────────────────────────────────────────────
# Historical tasks span up to 120 days in the past; upcoming tasks reach
# up to 180 days into the future.  ~40 % of tasks have past due dates to
# simulate a realistic backlog of both overdue and in-flight work.
_PAST_WINDOW_DAYS: Final[int] = 120
_FUTURE_WINDOW_DAYS: Final[int] = 180
_PAST_DATE_PROBABILITY: Final[float] = 0.40


class Command(BaseCommand):
    help = (
        "Seed the database with 50 Project and 200 Task records "
        "for local development and manual testing."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--reset",
            action="store_true",
            default=False,
            help=(
                "Truncate all existing Project and Task records before seeding. "
                "Without this flag the command exits early if data already exists."
            ),
        )

    def handle(self, *args, **options) -> None:
        random.seed(_RANDOM_SEED)

        with transaction.atomic():
            self._guard_existing_data(reset=options["reset"])
            projects: list[Project] = self._seed_projects()
            self._seed_tasks(projects)

        self.stdout.write(
            self.style.SUCCESS(
                f"\n✓ Seeding complete — "
                f"{_PROJECT_COUNT} projects and {_TASK_COUNT} tasks committed."
            )
        )

    # ── Step guards ────────────────────────────────────────────────────────────

    def _guard_existing_data(self, *, reset: bool) -> None:
        existing_projects: int = Project.objects.count()
        if existing_projects == 0:
            return

        if not reset:
            self.stdout.write(
                self.style.WARNING(
                    f"  {existing_projects} project(s) already exist. "
                    "Run with --reset to truncate and re-seed."
                )
            )
            raise SystemExit(0)

        self.stdout.write("  --reset flag detected; truncating existing records …")
        Task.objects.all().delete()
        Project.objects.all().delete()
        self.stdout.write(self.style.WARNING("  Existing records cleared."))

    # ── Project seeding ────────────────────────────────────────────────────────

    def _seed_projects(self) -> list[Project]:
        self.stdout.write(f"  Generating {_PROJECT_COUNT} project records …")

        names: list[str] = self._build_project_names()
        statuses: list[str] = self._distribute_statuses()

        project_objects: list[Project] = [
            Project(
                name=names[i],
                description=self._render_description(),
                status=statuses[i],
            )
            for i in range(_PROJECT_COUNT)
        ]

        # bulk_create for Projects avoids 50 individual INSERT round-trips.
        created: list[Project] = Project.objects.bulk_create(project_objects)
        self.stdout.write(f"  ✓ {len(created)} projects inserted.")
        return created

    def _build_project_names(self) -> list[str]:
        all_combos: list[tuple[str, str]] = list(
            itertools.product(_PROJECT_PREFIXES, _PROJECT_SUFFIXES)
        )
        random.shuffle(all_combos)
        return [f"{prefix} {suffix}" for prefix, suffix in all_combos[:_PROJECT_COUNT]]

    def _distribute_statuses(self) -> list[str]:
        # Realistic status spread: most projects active, a healthy tail of others.
        pool: list[str] = (
            [Project.Status.ACTIVE]    * 28 +
            [Project.Status.ON_HOLD]   * 10 +
            [Project.Status.COMPLETED] * 8  +
            [Project.Status.ARCHIVED]  * 4
        )
        random.shuffle(pool)
        return pool[:_PROJECT_COUNT]

    def _render_description(self) -> str:
        template: str = random.choice(_DESCRIPTION_TEMPLATES)
        return template.format(
            adjective=random.choice(_DESC_ADJECTIVES),
            layer=random.choice(_DESC_LAYERS),
            quarter=random.randint(1, 4),
        )

    # ── Task seeding ───────────────────────────────────────────────────────────

    def _seed_tasks(self, projects: list[Project]) -> None:
        self.stdout.write(
            f"  Generating {_TASK_COUNT} task records via bulk_create …"
        )

        today: date = date.today()
        task_objects: list[Task] = []

        for i in range(_TASK_COUNT):
            # Round-robin distribution: every project receives exactly
            # _TASK_COUNT // _PROJECT_COUNT tasks (200 / 50 = 4 each).
            project: Project = projects[i % _PROJECT_COUNT]
            due: date | None = self._generate_due_date(today)
            # Tasks whose due date is in the past have a high probability of
            # already being marked complete, mirroring a real-world backlog.
            complete: bool = (
                random.random() < 0.85
                if due is not None and due < today
                else random.random() < 0.15
            )

            task_objects.append(
                Task(
                    title=self._render_task_title(),
                    project=project,
                    assignee=random.choice(_ASSIGNEES + [None]),   # ~9 % unassigned
                    priority=random.choice(list(Task.Priority)),
                    due_date=due,
                    is_complete=complete,
                )
            )

        # Single batch INSERT — avoids 200 individual round-trips and keeps
        # the atomic block lean regardless of _TASK_COUNT.
        inserted: list[Task] = Task.objects.bulk_create(task_objects)
        self.stdout.write(f"  ✓ {len(inserted)} tasks bulk-inserted.")

    def _render_task_title(self) -> str:
        return f"{random.choice(_TASK_VERBS)} {random.choice(_TASK_OBJECTS)}"

    def _generate_due_date(self, today: date) -> date | None:
        if random.random() < 0.08:
            return None  # ~8 % of tasks have no due date

        if random.random() < _PAST_DATE_PROBABILITY:
            delta: int = random.randint(1, _PAST_WINDOW_DAYS)
            return today - timedelta(days=delta)

        delta = random.randint(1, _FUTURE_WINDOW_DAYS)
        return today + timedelta(days=delta)
