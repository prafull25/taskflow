from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class TaskFlowPagination(PageNumberPagination):
    """
    Standardised paginator for all TaskFlow API endpoints.

    Defaults: 20 items/page, deterministic ordering enforced per-viewset.
    Clients may request up to 100 items via ?page_size=N.
    """

    page_size: int = 20
    page_size_query_param: str = "page_size"
    max_page_size: int = 100

    def get_paginated_response(self, data: list) -> Response:
        return Response(
            {
                "pagination": {
                    "count": self.page.paginator.count,
                    "total_pages": self.page.paginator.num_pages,
                    "current_page": self.page.number,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                },
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict) -> dict:
        return {
            "type": "object",
            "properties": {
                "pagination": {
                    "type": "object",
                    "properties": {
                        "count": {"type": "integer"},
                        "total_pages": {"type": "integer"},
                        "current_page": {"type": "integer"},
                        "next": {"type": "string", "nullable": True},
                        "previous": {"type": "string", "nullable": True},
                    },
                },
                "results": schema,
            },
        }
