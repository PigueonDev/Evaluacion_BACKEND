# Blockbuster - Evaluación Sumativa #2 (Django + Django Admin)

Sistema web para el arriendo de películas, hecho con Django, MySQL/MariaDB y Bootstrap.
Continuación del proyecto de la Evaluación #1: se mantienen **dos aplicaciones** y la información pasó de JSON a base de datos relacional.

## Aplicaciones y modelos

| App | Modelo | Tabla | Finalidad |
|---|---|---|---|
| catalogoApp | Genero | `generos` | Clasifica las películas (Acción, Drama, etc.) |
| catalogoApp | Director | `directores` | Director de cada película |
| catalogoApp | Pelicula | `peliculas` | Películas disponibles para arriendo (FK a Genero y Director) |
| clientesApp | Cliente | `clientes` | Clientes del videoclub |
| clientesApp | Arriendo | `arriendos` | Arriendo de una película por un cliente (FK a Cliente y Pelicula) |

Relaciones: `Pelicula.genero -> Genero`, `Pelicula.director -> Director`, `Arriendo.cliente -> Cliente`, `Arriendo.pelicula -> Pelicula`.

## Instalación en EC2

### Amazon Linux 2023

Comprueba primero el sistema operativo:

```bash
cat /etc/os-release
```

En Amazon Linux 2023 utiliza `dnf`:

```bash
sudo dnf update -y
sudo dnf install -y python3 python3-pip python3-devel gcc pkg-config mariadb105-server mariadb-connector-c-devel git
sudo systemctl enable --now mariadb
```

### Ubuntu/Debian

En Ubuntu o Debian utiliza `apt`:

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential pkg-config default-libmysqlclient-dev git mariadb-server
sudo systemctl enable --now mariadb
```

### Instalación del proyecto

Continúa con estos pasos en cualquiera de los dos sistemas:

```bash

# Base de datos
sudo mysql -e "CREATE DATABASE blockbuster CHARACTER SET utf8mb4 COLLATE utf8mb4_spanish_ci;"
sudo mysql -e "CREATE USER 'user_blockbuster'@'localhost' IDENTIFIED BY 'TU_CLAVE';"
sudo mysql -e "GRANT ALL PRIVILEGES ON blockbuster.* TO 'user_blockbuster'@'localhost'; FLUSH PRIVILEGES;"

# Proyecto
git clone URL_DEL_REPOSITORIO
cd blockbuster
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Variables de entorno
cp .env.example .env
nano .env        # completar SECRET_KEY, ALLOWED_HOSTS (IP pública de la EC2) y datos de la BD

# Migraciones y datos
python manage.py migrate
python manage.py createsuperuser
python manage.py cargar_datos      # opcional: datos de ejemplo

# Ejecutar (abrir el puerto 8000 en el Security Group de la EC2)
python manage.py runserver 0.0.0.0:8000
```

Sitio: `http://IP_PUBLICA:8000/` — Admin: `http://IP_PUBLICA:8000/admin/`

## Variables de entorno (`.env`)

`SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_ENGINE`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`.
El archivo `.env` está en `.gitignore`; solo se sube `.env.example`.
