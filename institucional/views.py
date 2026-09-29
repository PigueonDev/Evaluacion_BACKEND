from django.shortcuts import render

from .models import Autoridad, Delegacion, Municipio


def inicio(request):
    municipio = Municipio.objects.first()
    delegaciones = Delegacion.objects.filter(activa=True)
    contexto = {
        "municipio": municipio,
        "delegaciones": delegaciones,
        "antiguedad": 2026 - municipio.fundacion if municipio else 0,
        "pagina_activa": "inicio",
    }
    return render(request, "institucional/inicio.html", contexto)


def autoridades(request):
    contexto = {
        "municipio": Municipio.objects.first(),
        "alcaldia": Autoridad.objects.filter(cargo__icontains="alcald").first(),
        "concejo": Autoridad.objects.exclude(cargo__icontains="alcald"),
        "total_autoridades": Autoridad.objects.filter(activa=True).count(),
        "delegaciones": Delegacion.objects.filter(activa=True),
        "pagina_activa": "autoridades",
    }
    return render(request, "institucional/autoridades.html", contexto)
