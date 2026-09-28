from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from catalogoApp.models import Genero, Director, Pelicula
from clientesApp.models import Cliente, Arriendo


class Command(BaseCommand):
    help = "Carga datos de ejemplo (géneros, directores, películas, clientes y arriendos)."

    def handle(self, *args, **options):
        generos = {n: Genero.objects.get_or_create(nombre=n, defaults={'descripcion': d})[0] for n, d in [
            ('Acción', 'Películas de acción y aventuras'),
            ('Comedia', 'Películas para reír'),
            ('Drama', 'Historias dramáticas'),
            ('Ciencia Ficción', 'Futuro, espacio y tecnología'),
            ('Terror', 'Películas de miedo'),
        ]}
        directores = {n: Director.objects.get_or_create(nombre=n, defaults={'nacionalidad': nac})[0] for n, nac in [
            ('Steven Spielberg', 'Estados Unidos'),
            ('Christopher Nolan', 'Reino Unido'),
            ('Guillermo del Toro', 'México'),
            ('Quentin Tarantino', 'Estados Unidos'),
        ]}
        datos = [
            ('Jurassic Park', 1993, 127, 'TE7', 2500, 1, 'Ciencia Ficción', 'Steven Spielberg', 'Un parque de dinosaurios clonados sale mal.'),
            ('Inception', 2010, 148, '14', 3000, 1, 'Ciencia Ficción', 'Christopher Nolan', 'Un ladrón entra en los sueños para plantar una idea.'),
            ('Interstellar', 2014, 169, 'TE7', 3000, 1, 'Ciencia Ficción', 'Christopher Nolan', 'Un grupo de astronautas viaja por un agujero de gusano.'),
            ('El Laberinto del Fauno', 2006, 118, '14', 2500, 1, 'Drama', 'Guillermo del Toro', 'Una niña descubre un mundo fantástico en plena posguerra.'),
            ('Pulp Fiction', 1994, 154, '18', 2500, 1, 'Acción', 'Quentin Tarantino', 'Historias cruzadas de criminales en Los Ángeles.'),
            ('Tiburón', 1975, 124, '14', 2000, 1, 'Terror', 'Steven Spielberg', 'Un tiburón blanco aterroriza una playa.'),
        ]
        peliculas = []
        for t, a, dur, cl, pr, st, g, d, s in datos:
            p, _ = Pelicula.objects.get_or_create(titulo=t, anio=a, defaults=dict(
                duracion=dur, clasificacion=cl, precio_arriendo=pr, stock=st, sinopsis=s,
                genero=generos[g], director=directores[d]))
            if p.stock != st:
                p.stock = st
                p.save(update_fields=['stock'])
            peliculas.append(p)

        clientes = []
        for run, n, pa, ma, mail, fono in [
            ('11111111-1', 'Juan', 'Pérez', 'Soto', 'juan@correo.cl', '+56911111111'),
            ('22222222-2', 'María', 'González', 'Rojas', 'maria@correo.cl', '+56922222222'),
            ('33333333-3', 'Pedro', 'Muñoz', 'Díaz', 'pedro@correo.cl', '+56933333333'),
        ]:
            c, _ = Cliente.objects.get_or_create(run=run, defaults=dict(
                nombre=n, paterno=pa, materno=ma, email=mail, telefono=fono))
            clientes.append(c)

        hoy = timezone.localdate()
        if not Arriendo.objects.exists():
            Arriendo.objects.create(cliente=clientes[0], pelicula=peliculas[0], fecha_limite=hoy + timedelta(days=3),
                                    estado='A', total=peliculas[0].precio_arriendo)
            Arriendo.objects.create(cliente=clientes[1], pelicula=peliculas[1], fecha_arriendo=hoy - timedelta(days=5),
                                    fecha_limite=hoy - timedelta(days=2), fecha_devolucion=hoy - timedelta(days=2),
                                    estado='D', total=peliculas[1].precio_arriendo)
            Arriendo.objects.create(cliente=clientes[2], pelicula=peliculas[4], fecha_arriendo=hoy - timedelta(days=8),
                                    fecha_limite=hoy - timedelta(days=5), estado='R', total=peliculas[4].precio_arriendo)
        self.stdout.write(self.style.SUCCESS("Datos de ejemplo cargados."))
