from django.db.models import Q
from django.shortcuts import render
from catalogoApp.models import Genero, Director, Pelicula
from clientesApp.models import Cliente


def inicio(request):
    """Página principal del proyecto: tarjetas hacia cada módulo."""
    data = {
        'total_peliculas': Pelicula.objects.count(),
        'total_clientes': Cliente.objects.count(),
    }
    return render(request, 'main.html', data)


def catalogo_home(request):
    data = {
        'total_peliculas': Pelicula.objects.count(),
        'total_generos': Genero.objects.count(),
        'total_directores': Director.objects.count(),
        'ultimas': Pelicula.objects.select_related('genero', 'director').order_by('-id')[:6],
    }
    return render(request, 'catalogo/inicio.html', data)


def listar_peliculas(request):
    q = request.GET.get('q', '').strip()
    peliculas = Pelicula.objects.select_related('genero', 'director')
    if q:
        peliculas = peliculas.filter(
            Q(titulo__icontains=q) | Q(genero__nombre__icontains=q) | Q(director__nombre__icontains=q)
        )
    return render(request, 'catalogo/peliculas.html', {'peliculas': peliculas, 'q': q})


def listar_generos(request):
    q = request.GET.get('q', '').strip()
    generos = Genero.objects.all()
    if q:
        generos = generos.filter(Q(nombre__icontains=q) | Q(descripcion__icontains=q))
    return render(request, 'catalogo/generos.html', {'generos': generos, 'q': q})


def listar_directores(request):
    q = request.GET.get('q', '').strip()
    directores = Director.objects.all()
    if q:
        directores = directores.filter(Q(nombre__icontains=q) | Q(nacionalidad__icontains=q))
    return render(request, 'catalogo/directores.html', {'directores': directores, 'q': q})
