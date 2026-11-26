from rest_framework.exceptions import NotAcceptable
from rest_framework.negotiation import DefaultContentNegotiation


class NegociacionJSON(DefaultContentNegotiation):
    """Si el cliente pide un formato que la vista no renderiza, responde en JSON en vez de 406.

    Las exportaciones devuelven el archivo Excel o PDF directamente; solo sus errores pasan por el renderer,
    y deben salir en JSON aunque Swagger envíe `Accept: application/pdf`.
    """

    def select_renderer(self, request, renderers, format_suffix=None):
        try:
            return super().select_renderer(request, renderers, format_suffix)
        except NotAcceptable:
            return renderers[0], renderers[0].media_type
