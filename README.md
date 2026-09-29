# Ilustre Municipalidad de La Serena — sitio informativo Django
# MVP Sistema de Gestión de Resultados · Evaluación Sumativa 2

## Qué incluye
Proyecto Django con dos aplicaciones (`institucional` y `servicios`) para registrar delegaciones, funcionarios, actividades, evidencias, compromisos y períodos de medición. El catálogo JSON se conserva como fuente de carga inicial, pero la aplicación consulta la base de datos mediante Django ORM.

## Requisitos
- Python 3.9 o superior
- SQLite para desarrollo local o MariaDB/MySQL para EC2

## Instalación y ejecución
En PowerShell, desde la carpeta del proyecto:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python generar_estaticos.py
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py createsuperuser
python manage.py runserver
```

Abrir http://127.0.0.1:8000/

## Rutas
| URL | Aplicación | Vista |
|---|---|---|
| `/` | institucional | Inicio / presentación |
| `/autoridades/` | institucional | Autoridades y delegaciones (ORM) |
| `/servicios/` | servicios | Catálogo filtrable (ORM) |
| `/servicios/<slug>/` | servicios | Ficha de trámite |
| `/servicios/dashboard/` | servicios | Panel SGR |
| `/servicios/actividades/` | servicios | Actividades y filtros |
| `/servicios/agenda/` | servicios | Agenda colectiva |
| `/admin/` | Django | Administración CRUD |

## Librería externa
Además de Django se usa **WhiteNoise** para servir archivos estáticos y **Pillow** para generar las imágenes institucionales locales.

## Datos y dominio SGR

`python manage.py cargar_datos_demo` carga información ficticia desde los JSON, crea las seis delegaciones territoriales y prepara un período abierto. Los datos reales de ciudadanos o funcionarios no deben utilizarse.

El dominio incluye delegaciones, cargos, funcionarios, servicios, ítems de medición, períodos, metas, actividades, evidencias, validaciones, compromisos, historial y auditoría. Las fórmulas de cumplimiento y semáforo están implementadas en el modelo `Meta`.

## Variables de entorno

Copia `.env.example` como `.env`. Para MariaDB/MySQL usa `DB_ENGINE=mysql` y completa las credenciales. En local, si no defines `DB_ENGINE`, se usa SQLite.

## Amazon Linux 2023 / EC2

```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip git mariadb105-server nginx
sudo systemctl enable --now mariadb
sudo mysql_secure_installation
mysql -u root -p
```

En MariaDB crea una base y un usuario de aplicación, luego configura `.env` con `DB_HOST=127.0.0.1`, `DB_PORT=3306`, `DB_NAME=sgr_laserena`, `DB_USER=sgr_user` y `DB_PASSWORD`.

```bash
git clone URL_DEL_REPOSITORIO
cd gestion_municipal_delegacion
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py cargar_datos_demo
python manage.py createsuperuser
python manage.py collectstatic --noinput
gunicorn --bind 0.0.0.0:8000 laserena.wsgi:application
```

En el grupo de seguridad de EC2 permite SSH (22) y HTTP (80). Para una ejecución persistente, configura Gunicorn como servicio systemd y usa Nginx como proxy inverso. No publiques el puerto de desarrollo en producción.

Archivos preparados en `deploy/`:

```bash
sudo cp deploy/laserena.service /etc/systemd/system/laserena.service
sudo cp deploy/nginx.conf /etc/nginx/conf.d/laserena.conf
sudo systemctl daemon-reload
sudo systemctl enable --now laserena
sudo systemctl enable --now nginx
sudo systemctl status laserena nginx
```

## Evidencias

La matriz inicial de trazabilidad está en `docs/MATRIZ_TRAZABILIDAD.md`. Debes complementarla con los commits, pruebas y capturas de tu equipo.

No hay modelos ni migraciones: el contenido se lee en las vistas y se envía al template por contexto.
