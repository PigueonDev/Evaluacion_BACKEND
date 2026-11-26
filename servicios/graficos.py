"""Series para los gráficos de carga de trabajo y de tendencia. El dibujo es SVG, sin bibliotecas externas."""

from datetime import timedelta


def barras(filas, ancho=640, alto=200):
	filas = [fila for fila in filas if fila.get("etiqueta")]
	if not filas:
		return {"vacio": True, "ancho": ancho, "alto": alto, "barras": []}
	maximo = max(fila["valor"] for fila in filas) or 1
	paso = (ancho - 24) / len(filas)
	ancho_barra = max(10, min(40, paso * 0.62))
	base = alto - 32
	dibujo = []
	for indice, fila in enumerate(filas):
		altura = (fila["valor"] / maximo) * (base - 16)
		x = 12 + indice * paso + (paso - ancho_barra) / 2
		dibujo.append({
			"x": round(x, 1),
			"y": round(base - altura, 1),
			"w": round(ancho_barra, 1),
			"h": round(max(altura, 0), 1),
			"tx": round(x + ancho_barra / 2, 1),
			"etiqueta": fila["etiqueta"],
			"valor": fila["valor"],
		})
	return {"vacio": False, "ancho": ancho, "alto": alto, "base": base, "barras": dibujo}


def linea(filas, ancho=640, alto=200):
	if not filas:
		return {"vacio": True, "ancho": ancho, "alto": alto, "puntos": "", "marcas": []}
	maximo = max(fila["valor"] for fila in filas) or 1
	total = max(len(filas) - 1, 1)
	base = alto - 32
	marcas = []
	for indice, fila in enumerate(filas):
		x = 28 + indice * (ancho - 48) / total
		y = 16 + (1 - (fila["valor"] / maximo)) * (base - 16)
		marcas.append({
			"x": round(x, 1),
			"y": round(y, 1),
			"etiqueta": fila["etiqueta"],
			"valor": fila["valor"],
		})
	return {
		"vacio": False,
		"ancho": ancho,
		"alto": alto,
		"base": base,
		"puntos": " ".join(f"{marca['x']},{marca['y']}" for marca in marcas),
		"marcas": marcas,
	}


def por_semana(fechas, inicio, termino):
	"""Cuenta registros por semana (lunes) entre las dos fechas, inclusive."""
	if inicio is None or termino is None or termino < inicio:
		return []
	conteo = {}
	for fecha in fechas:
		if fecha is None or fecha < inicio or fecha > termino:
			continue
		lunes = fecha - timedelta(days=fecha.weekday())
		conteo[lunes] = conteo.get(lunes, 0) + 1
	cursor = inicio - timedelta(days=inicio.weekday())
	filas = []
	while cursor <= termino:
		filas.append({"etiqueta": cursor.strftime("%d/%m"), "valor": conteo.get(cursor, 0)})
		cursor += timedelta(days=7)
	return filas
