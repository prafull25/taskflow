# Taskflow

A production-structured Django 5.x REST API for managing projects and tasks, built with Django REST Framework, PostgreSQL, and strict adherence to SOLID engineering principles.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | Django 5.x |
| API | Django REST Framework 3.15 |
| Database | PostgreSQL (psycopg3) |
| Filtering | django-filter 24.x |

---

## Project Structure

```
taskflow/
├── manage.py
├── taskflow/                        # Config package
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── projects/                        # Decoupled app
    ├── models.py                    # Project, Task models
    ├── serializers.py               # ProjectSerializer, TaskSerializer
    ├── views.py                     # ProjectViewSet, TaskViewSet
    ├── filters.py                   # TaskFilter (django-filter)
    ├── pagination.py                # TaskFlowPagination
    ├── admin.py                     # @admin.register config
    ├── urls.py                      # DefaultRouter
    ├── tests.py                     # APITestCase regression suite
    └── management/
        └── commands/
            └── seed_db.py           # Database seeding command
```

---

## Local Setup

### 1. Clone and activate the virtual environment

```bash
git clone <repo-url>
cd Python_django_ass
python3.12 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure the database

Create a PostgreSQL database and update `taskflow/settings.py` with your credentials:

```python
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "taskflow_db",
        "USER": "<your-pg-user>",
        "PASSWORD": "",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
```

Then create the database:

```bash
psql postgres -c "CREATE DATABASE taskflow_db;"
```

### 4. Run migrations

```bash
cd taskflow
python manage.py makemigrations
python manage.py migrate
```

### 5. Create a superuser

```bash
python manage.py createsuperuser
```

### 6. Seed the database with test data

```bash
python manage.py seed_db          # First-time seed
python manage.py seed_db --reset  # Truncate and re-seed
```

Inserts **50 Projects** and **200 Tasks** in a single `transaction.atomic()` block using `bulk_create`.

### 7. Start the development server

```bash
python manage.py runserver
```

---

## Data Models

### Project

| Field | Type | Constraints |
|---|---|---|
| `name` | CharField(200) | `unique`, `db_index` |
| `description` | TextField(5000) | nullable |
| `status` | CharField | choices: `active`, `on_hold`, `completed`, `archived` |
| `created_at` | DateTimeField | auto |
| `updated_at` | DateTimeField | auto |

### Task

| Field | Type | Constraints |
|---|---|---|
| `title` | CharField(300) | `db_index` |
| `project` | ForeignKey(Project) | `CASCADE`, `db_index` |
| `assignee` | CharField(150) | nullable, `db_index` |
| `priority` | IntegerField | choices: `1=Low`, `2=Medium`, `3=High`, `4=Critical` |
| `due_date` | DateField | nullable, `db_index` |
| `is_complete` | BooleanField | `db_index` |

Both models enforce DB-level `CheckConstraint` on their choice fields.

---

## REST API

Base URL: `http://127.0.0.1:8000/api/`

### Projects

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/projects/` | Paginated project list |
| POST | `/api/projects/` | Create a project |
| GET | `/api/projects/{id}/` | Retrieve a project |
| PUT | `/api/projects/{id}/` | Full update |
| PATCH | `/api/projects/{id}/` | Partial update |
| DELETE | `/api/projects/{id}/` | Delete a project |
| GET | `/api/projects/{id}/summary/` | Aggregated task stats (single query) |

### Tasks

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/tasks/` | Paginated task list |
| POST | `/api/tasks/` | Create a task |
| GET | `/api/tasks/{id}/` | Retrieve a task |
| PUT | `/api/tasks/{id}/` | Full update |
| PATCH | `/api/tasks/{id}/` | Partial update |
| DELETE | `/api/tasks/{id}/` | Delete a task |

### Filtering & Ordering

```bash
# Filter tasks by project, priority, and completion status
GET /api/tasks/?project=1&priority=3&is_complete=false

# Filter tasks by multiple priorities
GET /api/tasks/?priority__in=3,4

# Filter tasks by due date range
GET /api/tasks/?due_date__gte=2026-01-01&due_date__lte=2026-06-30

# Search projects by name
GET /api/projects/?search=Apollo

# Order tasks by due date ascending
GET /api/tasks/?ordering=due_date

# Control page size (max 100)
GET /api/tasks/?page_size=50&page=2
```

### Project Summary Response

```bash
GET /api/projects/1/summary/
```

```json
{
  "name": "Apollo Platform",
  "total_tasks": 12,
  "completed_tasks": 7,
  "open_tasks": 5,
  "completion_rate": 58.3
}
```

Executed as a **single annotated SQL query** using `Count` + conditional aggregation — no N+1.

### Pagination Envelope

All list endpoints return:

```json
{
  "pagination": {
    "count": 200,
    "total_pages": 10,
    "current_page": 1,
    "next": "http://127.0.0.1:8000/api/tasks/?page=2",
    "previous": null
  },
  "results": [...]
}
```

Default page size: **20**. Configurable via `?page_size=N` (max 100).

---

## Admin Interface

URL: `http://127.0.0.1:8000/admin/`

Configured with `@admin.register` decorators. Key optimisations:

- `list_select_related` on `TaskAdmin` — eliminates N+1 on the project column
- `prefetch_related("tasks")` on `ProjectAdmin` — powers the task count column
- Bulk actions: **Mark complete** / **Mark incomplete** via single `queryset.update()`
- `TaskInline` embedded on the Project change page

---

## Running Tests

```bash
python manage.py test projects --verbosity=2
```

```
test_nonexistent_project_fk_returns_400 ... ok
test_valid_project_fk_creates_task      ... ok
test_priority_filter_excludes_other_priorities         ... ok
test_priority_filter_returns_200_without_db_error      ... ok
test_priority_filter_returns_only_matching_tasks       ... ok

Ran 5 tests in 0.031s — OK
```

### What the tests cover

| Test | Regression pinned |
|---|---|
| `test_nonexistent_project_fk_returns_400` | `PrimaryKeyRelatedField` returns HTTP 400 (not 500) on unknown FK |
| `test_valid_project_fk_creates_task` | Happy-path FK validation still returns HTTP 201 |
| `test_priority_filter_returns_200_without_db_error` | `priority__icontains` on IntegerField removed; filter returns HTTP 200 |
| `test_priority_filter_returns_only_matching_tasks` | Filter returns only tasks matching the requested priority |
| `test_priority_filter_excludes_other_priorities` | Filter correctly excludes non-matching priorities |

---

## Key Engineering Decisions

### Single Responsibility Principle
Each module has one job: `models.py` owns schema, `serializers.py` owns validation, `views.py` owns HTTP dispatch, `filters.py` owns query filtering, `pagination.py` owns page shape.

### Database Integrity
- `CheckConstraint` on `status` and `priority` — invalid values are rejected at the DB layer, not just the application layer.
- `PrimaryKeyRelatedField(queryset=Project.objects.all())` — invalid FK values produce a structured HTTP 400 at serializer validation time, before any SQL write.

### Query Performance
- `select_related("project")` on `TaskViewSet` — single `INNER JOIN` instead of N+1 per-row lookups when resolving `project.name`.
- `annotate(task_count=Count(...), latest_due_date=Max(...))` on `ProjectViewSet` — both aggregates resolved in one `LEFT OUTER JOIN + GROUP BY` query.
- Compound indexes on `(status, -created_at)` and `(project, is_complete, -priority)` cover the most common admin and API query patterns.
