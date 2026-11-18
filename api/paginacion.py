from rest_framework.pagination import PageNumberPagination


class Paginacion(PageNumberPagination):
    page_size = 20
    page_query_param = "pagina"
    page_size_query_param = "tamano"
    max_page_size = 100
