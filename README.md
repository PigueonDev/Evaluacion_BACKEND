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
| `/servicios/dashboard/` | servicios | Panel SGR (solo personal) |
| `/servicios/actividades/` | servicios | Actividades y filtros (solo personal) |
| `/servicios/agenda/` | servicios | Agenda colectiva (solo personal) |
| `/acceso/` | institucional | Login "Acceso funcionarios" (solo cuentas staff) |
| `/administracion/` | institucional | (Solo personal) Panel con accesos a phpMyAdmin y Django Admin por tabla |
| `/acceso/verificar/` | institucional | Verificación de sesión usada por Nginx para proteger phpMyAdmin |
| `/admin/` | Django | Administración CRUD |

## Acceso funcionarios y phpMyAdmin

En la esquina superior derecha de todas las páginas está el botón **Acceso funcionarios**. Al iniciar sesión con una cuenta staff (por ejemplo, la creada con `createsuperuser`) se abre el panel `/administracion/`, que muestra cada recurso (sedes/delegaciones, funcionarios, servicios, actividades, etc.) con botones para **ver registros** o **agregar nuevo** directamente en phpMyAdmin, además de los equivalentes en Django Admin.

La URL de phpMyAdmin se configura con `PHPMYADMIN_URL` en `.env` (por defecto `/phpmyadmin/`). En EC2, `deploy/nginx.conf` publica phpMyAdmin en `/phpmyadmin/` y usa `auth_request` contra `/acceso/verificar/`: sin sesión staff en Django, Nginx redirige al login.

```bash
sudo dnf install -y php php-fpm php-mysqlnd php-mbstring php-xml php-json
sudo systemctl enable --now php-fpm
cd /tmp && curl -LO https://www.phpmyadmin.net/downloads/phpMyAdmin-latest-all-languages.tar.gz
sudo mkdir -p /usr/share/phpmyadmin
sudo tar xzf phpMyAdmin-latest-all-languages.tar.gz --strip-components=1 -C /usr/share/phpmyadmin
sudo cp /usr/share/phpmyadmin/config.sample.inc.php /usr/share/phpmyadmin/config.inc.php
# Edita config.inc.php y define $cfg['blowfish_secret'] con 32 caracteres aleatorios.
sudo mkdir -p /usr/share/phpmyadmin/tmp && sudo chown -R apache:apache /usr/share/phpmyadmin/tmp
sudo cp deploy/nginx.conf /etc/nginx/conf.d/laserena.conf
sudo nginx -t && sudo systemctl reload nginx
```

phpMyAdmin seguirá pidiendo el usuario de MariaDB (por ejemplo `sgr_user`), por lo que el acceso queda protegido por dos capas: la sesión de Django y las credenciales de la base de datos.

## Seguridad

### Protecciones en la aplicación

- **Paneles privados:** Panel SGR, Actividades, Agenda y Administración exigen una sesión de personal (`is_staff`). Un visitante que entra por URL es enviado a `/acceso/`, y esos enlaces no se muestran en el menú, en el pie de página ni en la portada. El catálogo, las fichas y las autoridades siguen siendo públicos.
- **Inyección SQL:** todas las consultas usan el ORM de Django (consultas parametrizadas). Los filtros `estado` y `categoria` solo aceptan valores de una lista blanca, las búsquedas se recortan a 100 caracteres y MariaDB trabaja en modo `STRICT_TRANS_TABLES`.
- **Fuerza bruta:** después de 5 intentos fallidos por IP y usuario, el login queda bloqueado 15 minutos. `/admin/login/` usa la misma vista, así que tampoco sirve para saltarse el bloqueo. Nginx además limita ambos logins a 10 peticiones por minuto por IP.
- **Contraseñas:** mínimo 10 caracteres, no pueden ser solo números, ni contraseñas comunes, ni parecidas al usuario.
- **XSS y clickjacking:** las plantillas escapan todo el contenido. La cabecera `Content-Security-Policy` solo permite scripts del propio sitio, y `X-Frame-Options: DENY` impide meter el sitio en un iframe.
- **Evidencias privadas:** los archivos de `/media/` solo se entregan al personal con sesión. Django revisa el permiso y Nginx entrega el archivo con `X-Accel-Redirect`. Solo se aceptan PDF, JPG, PNG y WEBP de hasta 5 MB, y se bloquean rutas con `../`.
- **Sesión y cookies:** las cookies de sesión y CSRF son `HttpOnly` y `SameSite=Lax`, y la sesión dura 2 horas y se cierra al cerrar el navegador. Las páginas vistas con sesión se envían con `Cache-Control: no-store`.
- **Registro de accesos:** cada login exitoso, fallido y cierre de sesión queda registrado con usuario e IP. Se ven con `sudo journalctl -u laserena | grep seguridad`.
- **Nginx:** oculta su versión, bloquea archivos ocultos (`.env`, `.git`) y bloquea las carpetas internas de phpMyAdmin (`setup`, `libraries`, `vendor`, etc.).
- Si `DEBUG=False` y no se definió `SECRET_KEY`, la aplicación no arranca.

### Endurecer el servidor EC2

1. **`SECRET_KEY` propia y `.env` privado:**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(50))"   # copia el resultado en SECRET_KEY
chmod 600 /var/www/negocio/.env
```

2. **HTTPS (lo más importante contra el robo de contraseñas):** sin HTTPS, las claves viajan sin cifrar. Let's Encrypt necesita un dominio; puedes usar uno gratis de [DuckDNS](https://www.duckdns.org) que apunte a la IP de tu EC2. En el grupo de seguridad abre el puerto 443 y luego:

```bash
sudo dnf install -y certbot python3-certbot-nginx
sudo certbot --nginx -d tusitio.duckdns.org --redirect
```

Después agrega `HTTPS=True` y el dominio en `ALLOWED_HOSTS` dentro de `.env`, y ejecuta `sudo systemctl restart laserena`. Con eso las cookies quedan `Secure`, se activa HSTS y Django redirige todo a HTTPS.

3. **phpMyAdmin:** prohíbe entrar como `root` y acorta la sesión.

```bash
echo "\$cfg['Servers'][1]['AllowRoot'] = false;" | sudo tee -a /usr/share/phpmyadmin/config.inc.php
echo "\$cfg['LoginCookieValidity'] = 1800;" | sudo tee -a /usr/share/phpmyadmin/config.inc.php
```

4. **MariaDB:** ejecuta `sudo mysql_secure_installation` (clave de root, sin usuarios anónimos, sin base `test`). Usa `sgr_user` solo con permisos sobre `sgr_laserena` y nunca abras el puerto 3306 en el grupo de seguridad.
5. **Grupo de seguridad:** HTTP 80 y HTTPS 443 abiertos a todos; SSH 22 solo desde **My IP**.
6. **Actualizaciones:** `sudo dnf upgrade -y` y `pip install -U -r requirements.txt` cada cierto tiempo.

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


PROFE TUVE QUE CAMBIAR DE IDEA PORQUE LA ORIGINAL ERA UN BLOCKBUSTER TODO ORDINARIO DE HECHO ESTA EL BACKUP AHI GUARDADO XD
