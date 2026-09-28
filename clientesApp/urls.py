from django.urls import path
from clientesApp import views

urlpatterns = [
    path('', views.clientes_home, name='clientes_home'),
    path('lista/', views.listar_clientes, name='clientes_lista'),
    path('arriendos/', views.listar_arriendos, name='clientes_arriendos'),
]
