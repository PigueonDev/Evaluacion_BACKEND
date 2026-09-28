from django.db.models import Q
from django.shortcuts import render
from clientesApp.models import Cliente, Arriendo


def clientes_home(request):
    data = {
        'total_clientes': Cliente.objects.count(),
        'total_arriendos': Arriendo.objects.count(),
        'pendientes': Arriendo.objects.filter(estado='A').count(),
        'ultimos': Arriendo.objects.select_related('cliente', 'pelicula')[:6],
    }
    return render(request, 'clientes/inicio.html', data)


def listar_clientes(request):
    q = request.GET.get('q', '').strip()
    clientes = Cliente.objects.all()
    if q:
        clientes = clientes.filter(
            Q(run__icontains=q) | Q(nombre__icontains=q) | Q(paterno__icontains=q) | Q(email__icontains=q)
        )
    return render(request, 'clientes/clientes.html', {'clientes': clientes, 'q': q})


def listar_arriendos(request):
    q = request.GET.get('q', '').strip()
    arriendos = Arriendo.objects.select_related('cliente', 'pelicula')
    if q:
        arriendos = arriendos.filter(
            Q(cliente__nombre__icontains=q) | Q(cliente__paterno__icontains=q)
            | Q(cliente__run__icontains=q) | Q(pelicula__titulo__icontains=q)
        )
    return render(request, 'clientes/arriendos.html', {'arriendos': arriendos, 'q': q})
