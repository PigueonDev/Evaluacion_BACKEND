from django.contrib import admin
from django.urls import path, include
from catalogoApp import views

admin.site.site_header = 'Blockbuster | Administración'
admin.site.site_title = 'Blockbuster Admin'
admin.site.index_title = 'Gestión del videoclub'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('catalogo/', include('catalogoApp.urls')),
    path('clientes/', include('clientesApp.urls')),
    path('', views.inicio, name='home'),
]
