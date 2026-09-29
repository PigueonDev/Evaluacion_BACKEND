"""Utilidades para leer y procesar archivos JSON sin base de datos."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def cargar_json(ruta: Path) -> Any:
    """Lee un archivo JSON con encoding UTF-8 y lo devuelve como estructura Python."""
    if not ruta.exists():
        return {}
    with ruta.open(encoding="utf-8") as archivo:
        return json.load(archivo)


def buscar_por_clave(items: list[dict], clave: str, valor: str) -> dict | None:
    """Recorre una lista de diccionarios y retorna el primero que coincida."""
    for item in items:
        if str(item.get(clave, "")).lower() == str(valor).lower():
            return item
    return None
