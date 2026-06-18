import django_filters

from .models import Task


class TaskFilter(django_filters.FilterSet):
    """
    Declarative filter set for the Task resource.

    Supports exact, range, and boolean lookups backed by the
    indexed columns defined on Task.Meta.
    """

    project = django_filters.NumberFilter(
        field_name="project__id",
        lookup_expr="exact",
    )
    priority = django_filters.ChoiceFilter(
        choices=Task.Priority.choices,
        field_name="priority",
    )
    priority__in = django_filters.BaseInFilter(
        field_name="priority",
        lookup_expr="in",
    )
    is_complete = django_filters.BooleanFilter(field_name="is_complete")
    due_date__gte = django_filters.DateFilter(field_name="due_date", lookup_expr="gte")
    due_date__lte = django_filters.DateFilter(field_name="due_date", lookup_expr="lte")
    assignee = django_filters.CharFilter(field_name="assignee", lookup_expr="icontains")

    class Meta:
        model = Task
        fields: list[str] = ["project", "priority", "is_complete", "assignee"]
