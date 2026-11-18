"""Exportación a Excel (openpyxl) y PDF (ReportLab) de las cartas y las actividades.

Las columnas dependen del perfil: el perfil Usuario no recibe los datos sensibles en ningún formato.
"""

import logging
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from laserena.permisos import grupo_usuario

registro = logging.getLogger("api")

MAXIMO_FILAS = 5000
AZUL_SGR = "1F3B73"
TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TIPO_PDF = "application/pdf"


def _texto_fecha(valor, formato="%d/%m/%Y"):
    return valor.strftime(formato) if valor else ""


# --- Columnas por recurso ------------------------------------------------------------------
# (encabezado, función que obtiene el valor, ancho Excel, sensible)

COLUMNAS_CARTAS = [
    ("Folio", lambda c: c.folio, 14, False),
    ("N° OP", lambda c: c.numero_oficina_partes, 10, False),
    ("Ingreso", lambda c: _texto_fecha(c.fecha_ingreso), 11, False),
    ("Para", lambda c: c.get_destinatario_display(), 11, False),
    ("Tipo", lambda c: c.get_tipo_display(), 12, False),
    ("Remitente", lambda c: c.remitente, 26, False),
    ("Contacto remitente", lambda c: c.contacto_remitente, 22, True),
    ("Asunto", lambda c: c.asunto, 34, False),
    ("Delegación", lambda c: c.delegacion.nombre, 16, False),
    ("Derivada a", lambda c: c.derivada_a.nombre_completo if c.derivada_a_id else (str(c.derivada_a_unidad) if c.derivada_a_unidad_id else ""), 22, False),
    ("Estado", lambda c: c.get_estado_display(), 13, False),
    ("Estado matriz", lambda c: c.get_resolucion_display(), 14, False),
    ("Plazo", lambda c: _texto_fecha(c.plazo_respuesta), 11, False),
    ("Respondida", lambda c: _texto_fecha(c.fecha_respuesta), 11, False),
    ("Registrada por", lambda c: c.registrada_por.username, 16, True),
]

COLUMNAS_ACTIVIDADES = [
    ("Código", lambda a: a.codigo_verificador or "", 15, False),
    ("Fecha", lambda a: _texto_fecha(a.fecha), 11, False),
    ("Funcionario", lambda a: a.funcionario.nombre_completo, 24, False),
    ("Delegación", lambda a: a.funcionario.delegacion.nombre, 16, False),
    ("Ítem", lambda a: a.item.nombre, 26, False),
    ("Actividad", lambda a: a.descripcion, 34, False),
    ("Acción", lambda a: a.accion, 30, False),
    ("Contacto", lambda a: a.contacto, 20, True),
    ("Teléfono", lambda a: a.telefono, 14, True),
    ("Derivado a", lambda a: a.derivado_a.nombre if a.derivado_a_id else "", 18, False),
    ("Estado", lambda a: a.get_estado_display(), 11, False),
    ("Tareas", lambda a: f"{a.tareas_realizadas}/{a.total_tareas}", 8, False),
]

RECURSOS = {
    "cartas": {"titulo": "Cartas de Oficina de Partes", "columnas": COLUMNAS_CARTAS},
    "actividades": {"titulo": "Actividades registradas", "columnas": COLUMNAS_ACTIVIDADES},
}


def columnas_para(recurso, completo):
    return [col for col in RECURSOS[recurso]["columnas"] if completo or not col[3]]


def _filas(queryset, columnas):
    return [[str(obtener(obj) or "") for _, obtener, _, _ in columnas] for obj in queryset[:MAXIMO_FILAS]]


def _nombre_archivo(recurso, extension):
    return f"sgr_{recurso}_{timezone.localdate():%Y-%m-%d}.{extension}"


# --- Excel ---------------------------------------------------------------------------------------


def generar_excel(recurso, queryset, completo, usuario):
    columnas = columnas_para(recurso, completo)
    wb = Workbook()
    ws = wb.active
    ws.title = recurso.capitalize()

    ws.append([f"SGR · Municipalidad de La Serena — {RECURSOS[recurso]['titulo']}"])
    ws.append([f"Generado el {timezone.localtime():%d/%m/%Y %H:%M} por {usuario.get_username()} (perfil {grupo_usuario(usuario)})"])
    if not completo:
        ws.append(["Perfil Usuario: se omiten los datos sensibles (contactos, teléfonos y cuentas)."])
    ws.append([])
    ws["A1"].font = Font(bold=True, size=14, color=AZUL_SGR)

    fila_encabezado = ws.max_row + 1
    ws.append([nombre for nombre, _, _, _ in columnas])
    borde = Border(bottom=Side(style="thin", color="999999"))
    for indice, (_, _, ancho, _) in enumerate(columnas, start=1):
        celda = ws.cell(row=fila_encabezado, column=indice)
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=AZUL_SGR)
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(indice)].width = ancho

    for fila in _filas(queryset, columnas):
        ws.append(fila)
        for celda in ws[ws.max_row]:
            celda.alignment = Alignment(vertical="top", wrap_text=True)
            celda.border = borde

    ws.freeze_panes = ws.cell(row=fila_encabezado + 1, column=1)
    ws.auto_filter.ref = f"A{fila_encabezado}:{get_column_letter(len(columnas))}{max(ws.max_row, fila_encabezado)}"

    respuesta = HttpResponse(content_type=TIPO_EXCEL)
    respuesta["Content-Disposition"] = f'attachment; filename="{_nombre_archivo(recurso, "xlsx")}"'
    wb.save(respuesta)
    return respuesta


# --- PDF ------------------------------------------------------------------------------------------


class NumberedCanvas(canvas.Canvas):
    """Canvas que dibuja encabezado, pie de página y «Página x de y» cuando ya conoce el total de páginas."""

    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for estado in self._saved_page_states:
            self.__dict__.update(estado)
            self._draw_footer(total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_footer(self, total):
        ancho, _ = self._pagesize
        self.saveState()
        self.setStrokeColor(colors.HexColor(f"#{AZUL_SGR}"))
        self.setLineWidth(0.6)
        self.line(0.5 * inch, 0.55 * inch, ancho - 0.5 * inch, 0.55 * inch)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawString(0.5 * inch, 0.35 * inch, "© 2026 Municipalidad de La Serena · Sistema de Gestión de Resultados (SGR)")
        self.drawRightString(ancho - 0.5 * inch, 0.35 * inch, f"Página {self._pageNumber} de {total}")
        self.restoreState()


def generar_pdf(recurso, queryset, completo, usuario):
    columnas = columnas_para(recurso, completo)
    respuesta = HttpResponse(content_type=TIPO_PDF)
    respuesta["Content-Disposition"] = f'attachment; filename="{_nombre_archivo(recurso, "pdf")}"'

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4), rightMargin=0.5 * inch, leftMargin=0.5 * inch, topMargin=0.5 * inch, bottomMargin=0.8 * inch,
        title=f"SGR · {RECURSOS[recurso]['titulo']}", author="SGR La Serena",
    )
    estilos = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle("TituloSGR", parent=estilos["Heading1"], fontSize=16, textColor=colors.HexColor(f"#{AZUL_SGR}"), alignment=TA_CENTER, spaceAfter=4)
    estilo_sub = ParagraphStyle("SubSGR", parent=estilos["Normal"], fontSize=9, alignment=TA_CENTER, textColor=colors.grey)
    estilo_celda = ParagraphStyle("CeldaSGR", parent=estilos["Normal"], fontSize=7, leading=8.5)
    estilo_encabezado = ParagraphStyle("EncabezadoSGR", parent=estilo_celda, textColor=colors.white, fontName="Helvetica-Bold")

    elementos = []
    logo = settings.BASE_DIR / "static" / "img" / "escudo_la_serena.png"
    try:
        if logo.exists():
            elementos.append(Image(str(logo), width=0.55 * inch, height=0.65 * inch))
    except Exception:  # noqa: BLE001  un logo dañado no debe impedir el informe
        registro.warning("No se pudo cargar el logo del informe PDF")
    elementos.append(Paragraph(f"Reporte de {RECURSOS[recurso]['titulo'].lower()}", estilo_titulo))
    elementos.append(Paragraph("Municipalidad de La Serena · Delegaciones municipales", estilo_sub))
    elementos.append(Paragraph(
        f"Fecha: {timezone.localtime():%d/%m/%Y %H:%M} · Generado por {usuario.get_username()} (perfil {grupo_usuario(usuario)})", estilo_sub,
    ))
    if not completo:
        elementos.append(Paragraph("Perfil Usuario: se omiten los datos sensibles (contactos, teléfonos y cuentas).", estilo_sub))
    elementos.append(Spacer(1, 0.18 * inch))

    filas = _filas(queryset, columnas)
    datos = [[Paragraph(nombre, estilo_encabezado) for nombre, _, _, _ in columnas]]
    datos += [[Paragraph(valor.replace("&", "&amp;").replace("<", "&lt;"), estilo_celda) for valor in fila] for fila in filas]
    if not filas:
        datos.append([Paragraph("Sin registros para los filtros indicados.", estilo_celda)] + [""] * (len(columnas) - 1))

    ancho_util = landscape(A4)[0] - inch
    total_relativo = sum(ancho for _, _, ancho, _ in columnas)
    tabla = Table(datos, colWidths=[ancho_util * ancho / total_relativo for _, _, ancho, _ in columnas], repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(f"#{AZUL_SGR}")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2F9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elementos.append(tabla)
    elementos.append(Spacer(1, 0.12 * inch))
    elementos.append(Paragraph(f"Total de registros: {len(filas)}", estilos["Normal"]))

    doc.build(elementos, canvasmaker=NumberedCanvas)
    respuesta.write(buffer.getvalue())
    return respuesta


GENERADORES = {"excel": generar_excel, "pdf": generar_pdf}


def exportar(recurso, formato, queryset, usuario, completo):
    return GENERADORES[formato](recurso, queryset, completo, usuario)
