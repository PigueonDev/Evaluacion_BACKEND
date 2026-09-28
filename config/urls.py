from django.contrib import admin
from django.urls import path, include
from catalogoApp import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('catalogo/', include('catalogoApp.urls')),
    path('clientes/', include('clientesApp.urls')),
    path('', views.inicio, name='home'),
]
