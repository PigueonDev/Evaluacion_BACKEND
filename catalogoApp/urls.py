from django.urls import path
from catalogoApp import views

urlpatterns = [
    path('', views.catalogo_home, name='catalogo_home'),
    path('peliculas/', views.listar_peliculas, name='catalogo_peliculas'),
    path('generos/', views.listar_generos, name='catalogo_generos'),
    path('directores/', views.listar_directores, name='catalogo_directores'),
]
