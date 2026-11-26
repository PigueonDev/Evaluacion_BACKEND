from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class Paginacion(PageNumberPagination):
    page_size = 20
    page_query_param = "pagina"
    page_size_query_param = "tamano"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response({
            "total": self.page.paginator.count,
            "siguiente": self.get_next_link(),
            "anterior": self.get_previous_link(),
            "resultados": data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "required": ["total", "resultados"],
            "properties": {
                "total": {"type": "integer", "example": 42, "description": "Total de registros que cumplen el filtro."},
                "siguiente": {"type": "string", "nullable": True, "format": "uri", "description": "Enlace a la página siguiente."},
                "anterior": {"type": "string", "nullable": True, "format": "uri", "description": "Enlace a la página anterior."},
                "resultados": schema,
            },
        }
