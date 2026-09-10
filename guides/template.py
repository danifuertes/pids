# -*- coding: utf-8 -*-
"""Genera la plantilla de informe (docx) para PIDS - Proyecto 2."""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

OUT = "/home/dfc/projects/classes/pids/pids/guides/PIDS-template.docx"

AZUL   = RGBColor(0x1F, 0x38, 0x64)
AZUL2  = RGBColor(0x2E, 0x5C, 0x8A)
GRIS   = RGBColor(0x59, 0x59, 0x59)
VERDE  = RGBColor(0x37, 0x6E, 0x37)
NARANJA = RGBColor(0x9C, 0x51, 0x00)
SHADE_HINT = "EAF1F8"
SHADE_HEAD = "1F3864"
SHADE_ROW  = "F2F2F2"

doc = Document()

# ----------------------------------------------------------------------------
# Configuracion de pagina y estilos
# ----------------------------------------------------------------------------
sec = doc.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = sec.right_margin = Cm(2.5)
sec.top_margin = Cm(2.2)
sec.bottom_margin = Cm(2.2)
sec.header_distance = Cm(1.2)
sec.footer_distance = Cm(1.2)

st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(11)
st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
st.paragraph_format.space_after = Pt(6)
st.paragraph_format.line_spacing = 1.15

for name, size, color, before, after in [
    ("Heading 1", 16, AZUL,  16, 8),
    ("Heading 2", 13, AZUL2, 12, 6),
    ("Heading 3", 11.5, AZUL2, 10, 4),
]:
    s = doc.styles[name]
    s.font.name = "Calibri"
    s.font.size = Pt(size)
    s.font.color.rgb = color
    s.font.bold = True
    s.paragraph_format.space_before = Pt(before)
    s.paragraph_format.space_after = Pt(after)
    s.paragraph_format.keep_with_next = True
    s.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

cap = doc.styles["Caption"]
cap.font.name = "Calibri"
cap.font.size = Pt(9)
cap.font.bold = False
cap.font.italic = True
cap.font.color.rgb = GRIS
cap.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
cap.paragraph_format.space_before = Pt(4)
cap.paragraph_format.space_after = Pt(10)

# ----------------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------------
def shade(el, color):
    tcPr = el._tc.get_or_add_tcPr() if hasattr(el, "_tc") else el._p.get_or_add_pPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), color)
    tcPr.append(sh)

def fixed_layout(t):
    """Evita que Word reajuste los anchos de columna."""
    t.autofit = False
    lay = OxmlElement("w:tblLayout")
    lay.set(qn("w:type"), "fixed")
    t._tbl.tblPr.append(lay)

def set_widths(t, widths):
    """Fija los anchos de columna en tcW y en tblGrid (es el que respetan Word y LibreOffice)."""
    fixed_layout(t)
    grid = t._tbl.find(qn("w:tblGrid"))
    for gridcol, w in zip(grid.findall(qn("w:gridCol")), widths):
        gridcol.set(qn("w:w"), str(int(Cm(w).twips)))
    for row in t.rows:
        for i, w in enumerate(widths):
            row.cells[i].width = Cm(w)

def borders(cell, color="B4C6E7", sz="8"):
    tcPr = cell._tc.get_or_add_tcPr()
    b = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        e = OxmlElement("w:" + side)
        e.set(qn("w:val"), "single")
        e.set(qn("w:sz"), sz)
        e.set(qn("w:color"), color)
        b.append(e)
    tcPr.append(b)

def field(par, code, placeholder=""):
    r = par.add_run()
    fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "begin"); r._r.append(fc)
    r = par.add_run()
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = code
    r._r.append(it)
    r = par.add_run()
    fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "separate"); r._r.append(fc)
    par.add_run(placeholder)
    r = par.add_run()
    fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), "end"); r._r.append(fc)

def seq(par, nombre):
    """Campo de numeracion automatica de Word (Figura/Tabla)."""
    field(par, f" SEQ {nombre} \\* ARABIC ", "X")

def p(text="", style=None, bold=False, italic=False, size=None, color=None,
      align=None, space_after=None, space_before=None):
    par = doc.add_paragraph(style=style)
    if text:
        r = par.add_run(text)
        r.bold, r.italic = bold, italic
        if size:  r.font.size = Pt(size)
        if color: r.font.color.rgb = color
    if align is not None: par.alignment = align
    if space_after is not None: par.paragraph_format.space_after = Pt(space_after)
    if space_before is not None: par.paragraph_format.space_before = Pt(space_before)
    return par

def h(text, level=1):
    return doc.add_heading(text, level=level)

def bullets(items, style="List Bullet", indent=None):
    for it in items:
        par = doc.add_paragraph(it, style=style)
        par.paragraph_format.space_after = Pt(2)
        if indent: par.paragraph_format.left_indent = Cm(indent)

def hint(title, lines=(), tips=None, preguntas=()):
    """Caja de ayuda sombreada. El alumno la elimina antes de entregar."""
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0)
    shade(c, SHADE_HINT)
    borders(c)
    set_widths(t, [16.0])
    first = c.paragraphs[0]
    first.paragraph_format.space_after = Pt(3)
    r = first.add_run("[ELIMINAR esta caja antes de entregar] " + title)
    r.bold = True; r.italic = True; r.font.size = Pt(9); r.font.color.rgb = AZUL

    def line(txt, **kw):
        par = c.add_paragraph()
        par.paragraph_format.space_after = Pt(2)
        par.paragraph_format.left_indent = Cm(0.35)
        par.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r = par.add_run(txt)
        r.italic = True; r.font.size = Pt(9)
        r.bold = kw.get("bold", False)
        r.font.color.rgb = kw.get("color", GRIS)

    for ln in lines:
        line("• " + ln)
    for q in preguntas:
        line("Pregunta: " + q, bold=True, color=NARANJA)
    if tips:
        line("Se valorará especialmente: " + tips, bold=True, color=VERDE)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return t

def placeholder(text="[Escriba aquí su texto.]"):
    return p(text, italic=True, color=GRIS)

def figure_ph(caption, multi=False):
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0)
    borders(c, color="BFBFBF", sz="6")
    set_widths(t, [16.0])
    par = c.paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(24)
    par.paragraph_format.space_after = Pt(24)
    r = par.add_run("[Inserte aquí su(s) figura(s)]" if multi else "[Inserte aquí la figura]")
    r.italic = True; r.font.size = Pt(9); r.font.color.rgb = GRIS
    cp = doc.add_paragraph(style="Caption")
    r = cp.add_run("Figura "); r.bold = True
    seq(cp, "Figura")
    for rr in cp.runs: rr.bold = True
    r = cp.add_run(". "); r.bold = True
    cp.add_run(caption)
    return t

def repeat_header(t):
    """Repite la fila de cabecera si la tabla se parte entre paginas."""
    trPr = t.rows[0]._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)

def table_ph(headers, rows, caption, widths=None, left_cols=()):
    cp = doc.add_paragraph(style="Caption")
    cp.paragraph_format.space_before = Pt(8)
    cp.paragraph_format.keep_with_next = True
    r = cp.add_run("Tabla "); r.bold = True
    seq(cp, "Tabla")
    for rr in cp.runs: rr.bold = True
    r = cp.add_run(". "); r.bold = True
    cp.add_run(caption)

    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, htxt in enumerate(headers):
        c = t.cell(0, i)
        shade(c, SHADE_HEAD)
        par = c.paragraphs[0]
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_after = Pt(2)
        r = par.add_run(htxt)
        r.bold = True; r.font.size = Pt(9); r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci, val in enumerate(row):
            if ri % 2 == 1:
                shade(cells[ci], SHADE_ROW)
            par = cells[ci].paragraphs[0]
            par.paragraph_format.space_after = Pt(2)
            par.alignment = (WD_ALIGN_PARAGRAPH.LEFT if ci == 0 or ci in left_cols
                             else WD_ALIGN_PARAGRAPH.CENTER)
            r = par.add_run(val)
            r.font.size = Pt(9.5)
            if val.startswith("["):
                r.italic = True; r.font.color.rgb = GRIS
    if widths:
        set_widths(t, widths)
    repeat_header(t)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)
    return t

def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

def block_divider(numero, titulo):
    page_break()
    for _ in range(3):
        p(space_after=0)
    t = doc.add_table(rows=1, cols=1)
    c = t.cell(0, 0)
    shade(c, SHADE_HEAD)
    borders(c, color="1F3864", sz="12")
    set_widths(t, [16.0])
    par = c.paragraphs[0]
    par.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par.paragraph_format.space_before = Pt(14)
    par.paragraph_format.space_after = Pt(4)
    r = par.add_run(f"BLOQUE {numero}")
    r.bold = True; r.font.size = Pt(13); r.font.color.rgb = RGBColor(0xBD, 0xD7, 0xEE)
    par2 = c.add_paragraph()
    par2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    par2.paragraph_format.space_after = Pt(14)
    r = par2.add_run(titulo)
    r.bold = True; r.font.size = Pt(19); r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    page_break()

# ----------------------------------------------------------------------------
# Encabezado y pie
# ----------------------------------------------------------------------------
sec.different_first_page_header_footer = True

hdr = sec.header.paragraphs[0]
hdr.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = hdr.add_run("Proyectos en Ingeniería de Datos y Sistemas (PIDS) — Universidad Politécnica de Madrid\n")
r.font.size = Pt(8); r.font.color.rgb = GRIS
r = hdr.add_run("Proyecto 2: Sistema de detección de vehículos y conducción autónoma")
r.font.size = Pt(8); r.font.color.rgb = GRIS; r.italic = True
pb = OxmlElement("w:pBdr")
bt = OxmlElement("w:bottom")
bt.set(qn("w:val"), "single"); bt.set(qn("w:sz"), "6"); bt.set(qn("w:color"), "BFBFBF")
bt.set(qn("w:space"), "4")
pb.append(bt)
hdr._p.get_or_add_pPr().append(pb)

ftr = sec.footer.paragraphs[0]
ftr.alignment = WD_ALIGN_PARAGRAPH.CENTER
ftr.add_run("Página ")
field(ftr, " PAGE ", "1")
ftr.add_run(" de ")
field(ftr, " NUMPAGES ", "1")
for r in ftr.runs:
    r.font.size = Pt(8); r.font.color.rgb = GRIS

# ============================================================================
# PORTADA
# ============================================================================
p(space_after=0)
p("UNIVERSIDAD POLITÉCNICA DE MADRID", bold=True, size=12, color=AZUL2,
  align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0)
p("Escuela Técnica Superior de Ingenieros de Telecomunicación", size=10.5,
  color=GRIS, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=0)
p("Grupo de Tratamiento de Imágenes", size=10.5, color=GRIS,
  align=WD_ALIGN_PARAGRAPH.CENTER, space_after=24)

p("Proyectos en Ingeniería de Datos y Sistemas (PIDS)", size=12, italic=True,
  color=GRIS, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
p("Proyecto 2", size=12, bold=True, color=AZUL2,
  align=WD_ALIGN_PARAGRAPH.CENTER, space_after=18)

par = p(align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6)
r = par.add_run("Sistema de detección de vehículos\ny conducción autónoma")
r.bold = True; r.font.size = Pt(26); r.font.color.rgb = AZUL
par.paragraph_format.line_spacing = 1.0

par = p(align=WD_ALIGN_PARAGRAPH.CENTER, space_after=26)
r = par.add_run("MEMORIA DEL PROYECTO")
r.bold = True; r.font.size = Pt(13); r.font.color.rgb = GRIS

t = doc.add_table(rows=0, cols=2)
t.style = "Table Grid"
t.alignment = WD_TABLE_ALIGNMENT.CENTER
for k, v in [
    ("Grupo", "[Grupo]"),
    ("Autores", "[Apellidos, Nombre]\n[Apellidos, Nombre]\n[Apellidos, Nombre]\n[Apellidos, Nombre]"),
    ("Entrega", "[  ] Entrega 1 — Bloque 1\n[  ] Entrega 2 — Bloques 1 y 2\n[  ] Entrega 3 — Bloques 1, 2 y 3"),
    ("Fecha de entrega", "[dd/mm/aaaa]"),
    ("Curso académico", "2026/2027"),
]:
    cells = t.add_row().cells
    shade(cells[0], "D9E2F3")
    par = cells[0].paragraphs[0]
    par.paragraph_format.space_after = Pt(2)
    r = par.add_run(k); r.bold = True; r.font.size = Pt(10); r.font.color.rgb = AZUL
    first = True
    for line in v.split("\n"):
        par = cells[1].paragraphs[0] if first else cells[1].add_paragraph()
        first = False
        par.paragraph_format.space_after = Pt(2)
        r = par.add_run(line); r.font.size = Pt(10)
        if line.startswith("["): r.italic = True; r.font.color.rgb = GRIS

set_widths(t, [4.5, 11.5])

p(space_after=0)
hint("Marque con una X la casilla de la entrega correspondiente y actualice la fecha en cada una de las tres entregas.",
     ["Este informe es INCREMENTAL: se entrega tres veces, ampliando y corrigiendo el documento anterior. No cree un documento nuevo para cada bloque."])

# ============================================================================
# COMO USAR LA PLANTILLA
# ============================================================================
page_break()
h("Cómo usar esta plantilla", 1)
hint("ESTA SECCIÓN COMPLETA («Cómo usar esta plantilla») debe eliminarse antes de la entrega, "
     "junto con todas las cajas azules del documento.",
     ["Las cajas azules son ayuda para el alumno y NO cuentan para el límite de páginas… porque no deben estar en el documento entregado.",
      "Se entrega un único fichero PDF (exportado desde este .docx) con el nombre: PIDS_grupoX_entregaN.pdf"])

h("Entregas y contenido", 2)
table_ph(
    ["Entrega", "Bloques incluidos en el documento", "Límite de páginas*"],
    [["Entrega 1", "Bloque 1 (revisión inicial)", "10"],
     ["Entrega 2", "Bloque 1 corregido + Bloque 2", "20"],
     ["Entrega 3", "Bloques 1 y 2 corregidos + Bloque 3", "30"]],
    "Calendario de entregas y extensión máxima del informe.",
    widths=[3.0, 9.0, 3.5], left_cols=(1,))
p("* El límite de páginas se refiere al cuerpo del informe. NO cuentan para el límite: la portada, "
  "el índice, la respuesta a la revisión anterior, el reparto del trabajo, las referencias y los anexos. "
  "Los informes que superen el límite se evaluarán únicamente hasta la última página permitida.",
  size=9.5, italic=True, color=GRIS)

h("Trabajo incremental", 2)
p("En cada entrega se corrige lo anterior y se añade lo nuevo. Para que el profesorado pueda seguir "
  "la evolución del documento:")
bullets([
    "Rellene la tabla «Respuesta a la revisión anterior» indicando, para cada comentario recibido, qué se ha modificado y en qué sección.",
    "Mantenga la estructura y la numeración de secciones de esta plantilla.",
])

h("Normas de formato", 2)
bullets([
    "Fuente Calibri 11, interlineado 1,15, márgenes de 2,5 cm. No modifique estos valores para ganar espacio.",
    "Todas las figuras y tablas deben ir numeradas, con pie/encabezado descriptivo, y deben citarse en el texto (p. ej. «como se observa en la Figura 3…»). Una figura que no se comenta en el texto no puntúa.",
    "Los ejes, leyendas y unidades de las gráficas deben ser legibles al tamaño en el que se insertan.",
    "Las afirmaciones cuantitativas deben apoyarse en datos propios (tablas o figuras del informe), no en impresiones.",
    "Cite el software y las fuentes externas utilizadas en la sección de Referencias.",
    "No incluya capturas de código en el cuerpo del informe: si es imprescindible mostrar código, llévelo a un anexo y explique en el cuerpo qué hace y por qué.",
])

# ============================================================================
# RESPUESTA A LA REVISION + REPARTO
# ============================================================================
page_break()
h("Respuesta a la revisión anterior", 1)
hint("Rellene esta tabla en las entregas 2 y 3. En la entrega 1 escriba «No aplica».",
     ["Incluya TODOS los comentarios recibidos del profesorado, también aquellos con los que no esté de acuerdo (en ese caso, justifique por qué no se ha modificado).",
      "Esta tabla permite comprobar rápidamente que las correcciones se han incorporado; su ausencia penaliza la nota de la entrega."])
table_ph(
    ["#", "Comentario recibido", "Sección modificada", "Cambio realizado"],
    [["1", "[Comentario del profesor]", "[2.1]", "[Qué se ha cambiado.]"],
     ["2", "[…]", "[…]", "[…]"],
     ["3", "[…]", "[…]", "[…]"]],
    "Trazabilidad de las correcciones respecto a la entrega anterior.",
    widths=[1.0, 6.4, 3.0, 5.6], left_cols=(1, 3))

h("Reparto del trabajo", 1)
hint("Indique la participación real de cada miembro en cada bloque. Actualice la tabla en cada entrega.",
     ["El reparto no tiene por qué ser idéntico en todos los bloques, pero todos los miembros deben participar en todas las fases."])
table_ph(
    ["Integrante", "Bloque 1", "Bloque 2", "Bloque 3"],
    [["[Nombre 1]", "[Tareas]", "[Tareas]", "[Tareas]"],
     ["[Nombre 2]", "[Tareas]", "[Tareas]", "[Tareas]"],
     ["[Nombre 3]", "[Tareas]", "[Tareas]", "[Tareas]"],
     ["[Nombre 4]", "[Tareas]", "[Tareas]", "[Tareas]"]],
    "Reparto del trabajo entre los integrantes del grupo.",
    widths=[3.4, 4.0, 4.0, 4.6], left_cols=(1, 2, 3))

# ============================================================================
# INDICE
# ============================================================================
page_break()
h("Índice", 1)
hint("Para actualizar el índice: clic derecho sobre él → «Actualizar campos» → «Actualizar toda la tabla» (o seleccionar todo y pulsar F9). Hágalo justo antes de exportar a PDF.")
par = doc.add_paragraph()
field(par, ' TOC \\o "1-2" \\h \\z \\u ',
      "«Haga clic aquí y pulse F9 para generar el índice»")
for r in par.runs:
    r.font.size = Pt(10)

# ============================================================================
# BLOQUE 1
# ============================================================================
block_divider(1, "Recolección, anotación, análisis\ny depuración de datos")

h("1. Introducción", 1)
hint("Sección común a las tres entregas. Extensión máxima: 1 página.",
     ["Escríbala pensando en un lector técnico que NO conoce la asignatura ni el guion de prácticas.",
      "No copie literalmente el enunciado: reformule el problema con sus palabras."])

h("1.1. Contexto y motivación", 2)
hint("¿Qué problema se resuelve y por qué es relevante?",
     ["Detección de objetos sobre imágenes capturadas por un robot móvil (RoboMaster) para localizar robots adversarios.",
      "Relacione el problema con aplicaciones reales (percepción en conducción autónoma, robótica móvil, vigilancia…).",
      "Comente brevemente por qué el problema no es trivial: cámara en movimiento, oclusiones, iluminación variable, objetos pequeños, ejecución en tiempo real, etc."])
placeholder()

h("1.2. Objetivos del proyecto", 2)
hint("Enumere los objetivos globales del proyecto.",
     ["Distinga entre el objetivo final (detectar robots adversarios desde el propio robot y actuar en consecuencia) y los objetivos parciales de cada bloque."])
placeholder()

h("2. Recolección de datos", 1)
hint("Extensión orientativa: 1 página.",
     ["Describa el proceso realmente seguido y compárelo con el proceso ideal. Si algo salió mal, cuéntelo: forma parte del análisis.",
      "El objetivo es que un tercero pueda reproducir sus experimentos."])

h("2.1. Estrategia y condiciones de captura", 2)
hint("Justifique CÓMO decidió grabar, no solo qué grabó.",
     ["Escenarios, iluminación, oclusiones, distancias y orientaciones de los robots, movimiento de la cámara…",
      "Explique qué variabilidad buscaba cubrir con cada decisión."],
     tips="que la variabilidad de la captura esté planificada y argumentada en términos de la capacidad de generalización del modelo.")
placeholder()

h("2.2. Extracción de imágenes", 2)
hint("Justifique numéricamente el valor de INTERVAL empleado en video2frames.ipynb.",
     ["Justifique su elección de INTERVAL teniendo en cuenta que: nº de imágenes extraídas ≈ (fps × duración total) / INTERVAL.",
      "Razone el compromiso entre redundancia (INTERVAL pequeño: imágenes casi idénticas y coste de anotación elevado) y escasez de datos (INTERVAL grande).",
      "Indique el número final de imágenes extraídas y el total (mínimo exigido: 800, aunque es recomendable no extraer un número muy elevado de imágenes para evitar tiempos largos de entrenamiento en el bloque 2)."])
placeholder()
table_ph(
    ["Secuencia", "Duración (s)", "Resolución", "fps", "Frames extraídos", "Descripción del escenario"],
    [["video1", "[  ]", "[  ]", "[  ]", "[  ]", "[Breve descripción: entorno, iluminación, nº de robots…]"],
     ["video2", "[  ]", "[  ]", "[  ]", "[  ]", "[  ]"],
     ["video3", "[  ]", "[  ]", "[  ]", "[  ]", "[  ]"],
     ["Total", "[  ]", "—", "—", "[  ]", "—"]],
    "Resumen de las secuencias capturadas y de las imágenes extraídas de cada una.",
    widths=[2.1, 1.8, 2.3, 1.0, 2.0, 6.8], left_cols=(5,))

h("3. Anotación de datos", 1)
hint("Extensión orientativa: 1 página. Describa los criterios de anotación adoptados con labelImg.",
     ["¿Se anotan los robots parcialmente ocluidos? ¿A partir de qué porcentaje visible? ¿Y los robots muy pequeños, desenfocados o cortados por el borde de la imagen?",
      "¿El bounding box se ciñe al chasis o incluye torreta, cañón y antenas?",
      "Recuerde: la red aprenderá a predecir cajas tal y como usted las dibuje. Explique qué implicaciones tiene el criterio elegido."],
     tips="tener un criterio explícito, homogéneo entre anotadores y justificado en función del uso final del detector.")
placeholder()
figure_ph("Ejemplos de anotación: casos estándar y casos límite.", multi=True)

h("4. Análisis exploratorio de los datos (EDA)", 1)
hint("Extensión orientativa: 4 páginas. Es la sección con mayor peso en la nota del bloque. Rellene y comente la tabla "
     "de estadísticas básicas, comente los análisis de eda.ipynb aplicados a SU conjunto de datos y amplíe el análisis "
     "con todo aquello que considere oportuno, siempre debidamente justificado.",
     ["Cada figura/tabla debe ir acompañada de su lectura: qué se observa y qué consecuencia tiene para el proceso de entrenamiento. Una figura/tabla sin interpretación no puntúa.",
      "Interprete los resultados: ¿está el conjunto equilibrado entre secuencias? ¿Predominan los objetos pequeños o grandes? ¿Hay secuencias claramente distintas del resto?",
      "Para cada análisis que añada por su cuenta: qué mide, POR QUÉ lo ha elegido y qué ha revelado sobre sus datos."],
     preguntas=["El notebook analiza la distribución de los canales RGB por secuencia. ¿Es este análisis "
                "determinante para caracterizar la iluminación de las escenas? ¿Se le ocurre una forma más "
                "adecuada de analizarla? Razone su respuesta y, si procede, sustituya o complemente el análisis."],
     tips="que cada análisis responda a una pregunta concreta sobre el conjunto de datos y que esa pregunta quede contestada.")
table_ph(
    ["Estadística", "Valor"],
    [["Número de secuencias", "[  ]"],
     ["Número total de imágenes", "[  ]"],
     ["Número medio de imágenes por secuencia", "[  ]"],
     ["Número total de bounding boxes", "[  ]"],
     ["Número medio de bounding boxes por imagen", "[  ]"],
     ["Área media de los bounding boxes (kilopíxeles cuadrados)", "[  ]"],
     ["Área mínima / máxima de los bounding boxes (kilopíxeles cuadrados)", "[  ]  /  [  ]"],
     ["Porcentaje de imágenes sin ningún bounding box", "[  ] %"]],
    "Estadísticas básicas del conjunto de datos.",
    widths=[10.0, 6.0])
placeholder()
figure_ph("Análisis exploratorio del conjunto de datos.", multi=True)

h("5. Aumento de datos (data augmentation)", 1)
hint("Extensión orientativa: 2 páginas. Indique las técnicas finalmente empleadas y justifíquelas.",
     ["Rellene la tabla con las transformaciones que haya decidido emplear: puede mantener las que trae data_aug.ipynb, eliminar las que descarte y añadir otras nuevas.",
      "Justifique brevemente qué variabilidad real simula cada técnica y, si ha descartado alguna, por qué.",
      "Catálogo de transformaciones: https://albumentations.ai/explore/ y https://albumentations.ai/docs/api-reference/"],
     tips="la coherencia entre las transformaciones elegidas y el dominio real de aplicación.")
table_ph(
    ["Técnica", "p", "Justificación (qué variabilidad simula)"],
    [["[Técnica 1]", "[  ]", "[…]"],
     ["[Técnica 2]", "[  ]", "[…]"],
     ["[Técnica 3]", "[  ]", "[…]"],
     ["[…]", "[  ]", "[…]"]],
    "Técnicas de aumento de datos empleadas y su justificación.",
    widths=[5.0, 1.4, 9.6], left_cols=(2,))
placeholder()
figure_ph("Ejemplos de imágenes aumentadas con sus bounding boxes transformados.", multi=True)

h("6. Depuración de datos", 1)
hint("Extensión orientativa: 1 página. Comente qué problemas ha detectado en sus datos, cómo los ha detectado y qué ha hecho con ellos.",
     ["Utilice criterios reproducibles y, a ser posible, apoyados en las métricas calculadas en el EDA. Indique cuántas imágenes se ven afectadas por cada criterio.",
      "Si NO ha encontrado nada que depurar, dígalo explícitamente y explique cómo ha llegado a esa conclusión: ¿qué ha revisado y con qué criterio? Afirmar que los datos son correctos sin mostrar cómo se ha comprobado no puntúa.",
      "Tenga en cuenta el riesgo de depurar en exceso: eliminar todos los casos difíciles produce un conjunto fácil y un modelo que falla en la realidad."])
placeholder()

# ============================================================================
# BLOQUE 2
# ============================================================================
block_divider(2, "Entrenamiento y evaluación\ndel modelo de detección")

hint("Este bloque se completa en la SEGUNDA entrega, junto con las correcciones del Bloque 1.",
     ["No borre estas secciones en la Entrega 1: déjelas como están para conservar la estructura del informe.",
      "Recuerde que en la Entrega 2 debe rellenar además la tabla «Respuesta a la revisión anterior».",
      "Todo este bloque se apoya en los notebooks train.ipynb y test.ipynb de la carpeta week2."])

# ---------------------------------------------------------------- 7. Pipeline
h("7. El pipeline de entrenamiento", 1)
hint("Extensión orientativa: 1 página. Represente con una figura de bloques conectados cómo se procesa una imagen "
     "desde que sale del disco hasta que acaba modificando los pesos de la red, y explíquela. Es la sección que "
     "demuestra que entiende y puede describir el sistema completo.",
     ["La figura es suya: decida qué módulos aparecen, cómo se conectan y qué nivel de detalle necesita. No copie "
      "un diagrama de internet: dibuje el pipeline que ha usado realmente.",
      "Basta con una descripción de ALTO NIVEL de cada módulo y de lo que le entrega al siguiente. Por ejemplo: el "
      "generador de datos toma imágenes del conjunto de entrenamiento y alimenta con ellas al modelo; el modelo "
      "produce predicciones; esas predicciones se comparan con las anotaciones para obtener la función de pérdida; "
      "el optimizador usa esa pérdida para actualizar los pesos de la red… y así sucesivamente.",
      "Explique qué es un batch y qué es un epoch, y por qué las imágenes se procesan por batches en lugar de "
      "todas a la vez.",
      "Explique en qué se diferencia la fase de validación de la de entrenamiento y por qué en ella no se "
      "actualizan los pesos."],
     tips="que la figura y el texto expliquen el mecanismo de entrenamiento/aprendizaje.")
placeholder()
figure_ph("Pipeline de entrenamiento.")

# ---------------------------------------------------------------- 8. Modelos
h("8. Modelos", 1)
hint("Extensión orientativa: 1 página. Describa BREVEMENTE cada uno de los modelos que haya comparado y "
     "explique el transfer learning que se está aplicando.",
     ["Una descripción corta por modelo —unas pocas frases— basta: en qué familia se encuadra, qué idea lo "
      "caracteriza y en qué se diferencia de los demás. No se espera un análisis exhaustivo, pero sí un mínimo de investigación.",
      "Use los nombres reales de las arquitecturas, no las claves del notebook: escriba «Faster R-CNN con backbone "
      "ResNet50-FPN», no «faster_rcnn_v1».",
      "Explique qué es un BACKBONE y qué papel cumple dentro de un detector.",
      "Transfer learning: qué es, de qué conjunto de datos vienen los pesos preentrenados, qué parte concreta de "
      "la red se modifica para utilizar transfer learning y por qué es determinante utilizarlo en este proyecto."],
     preguntas=["¿Qué esperaría que ocurriese si entrenase el mismo modelo desde cero, sin pesos preentrenados, "
                "con sus imágenes? Razone la respuesta y, si dispone de tiempo, compruébelo."])
placeholder()

# ---------------------------------------------------------------- 9. Hiperparametros
h("9. Hiperparámetros", 1)
hint("Extensión orientativa: 1 página. Esta sección DESCRIBE los hiperparámetros: qué es cada uno y qué efecto "
     "tiene sobre el entrenamiento. Los experimentos y los valores elegidos se deberían explicar en la sección 11.",
     ["Céntrese en los tres que de verdad va a tener que ajustar (batch size, learning rate y número de epochs) y "
      "dedíqueles el grueso de la sección.",
      "Mencione el resto (optimizador y sus parámetros, learning-rate scheduler, etc.) de forma más breve: basta "
      "con dejar claro para qué sirven.",
      "Del optimizador basta una descripción breve: qué hace y qué parámetros propios tiene. Si ha hecho "
      "experimentos con otros optimizadores, descríbalos aquí también.",
      "Explique qué hace el learning-rate scheduler y por qué el learning rate no tiene por qué ser constante "
      "durante todo el entrenamiento."],
     preguntas=["¿Qué ocurre con un batch size muy pequeño? ¿Y con uno muy grande? ¿Aparece algún error de "
                "ejecución y por qué?",
                "¿Qué ocurre con un learning rate muy alto? ¿Y muy bajo? ¿Afecta al número de epochs necesarios?",
                "¿Hasta cuándo merece la pena seguir entrenando? ¿Qué le indica que debe parar?"])
placeholder()

# ---------------------------------------------------------------- 10. Metricas
h("10. Métricas", 1)
hint("Extensión orientativa: 1 página. Explique las métricas antes de usarlas. El objetivo es que quede claro "
     "qué significan exactamente los resultados que va a presentar en la sección siguiente.",
     ["IoU (Intersection over Union): cómo se calcula entre una caja predicha y una real, y cómo se usa, junto con "
      "un umbral, para decidir si una detección cuenta como acierto.",
      "A partir de ahí, defina verdadero positivo, falso positivo y falso negativo en detección de objetos.",
      "Precisión y recall: qué mide cada una, en qué se diferencian y por qué normalmente hay un compromiso entre "
      "ambas. Relaciónelas con el umbral de confianza de las detecciones.",
      "Curva precisión-recall y AP (Average Precision): qué representa la curva y cómo se resume en un único "
      "número.",
      "mAP: qué añade la «m» al «AP». Explique la diferencia entre mAP, mAP@0.50 y mAP@0.75."],
     tips="entender qué mide realmente la métrica, no solo saber que «más alto es mejor».")
placeholder()

# ---------------------------------------------------------------- 11. Experimentos
h("11. Experimentos", 1)
hint("Extensión orientativa: 6 páginas. Es la sección con más peso del bloque: aquí cuenta qué probó, qué obtuvo "
     "y qué concluyó. Los resultados se miden sobre el conjunto de test con las métricas de la sección 10.",
     ["Siga este orden (para no alargar en exceso los experimentos): (1) ajuste los hiperparámetros con un único modelo; "
      "(2) con los hiperparámetros ya fijados, compare varias arquitecturas; (3) solo al final, reentrene el mejor "
      "modelo añadiendo los datos aumentados del Bloque 1 para intentar un último empujón/mejora. Hacer TODOS los "
      "experimentos con datos aumentados multiplicaría el tiempo de entrenamiento sin aportar información nueva.",
      "Documente también los experimentos que salieron mal: un experimento fallido bien explicado vale más que un "
      "valor acertado sin justificar.",
      "Centre cada experimento en una única prueba, o no podrá atribuir la mejora a nada concreto.",
      "Termine afirmando cuál es el modelo elegido y una justificación de por qué es el mejor para llevarlo al "
      "robot en el Bloque 3.",
      "Presente los resultados en el formato que prefiera (tablas, gráficas o ambas), pero de forma que se puedan "
      "comparar de un vistazo. Apóyese también en las curvas de pérdida y de learning rate: ¿qué forma tienen? "
      "¿Hay sobreajuste, subajuste o ruido? ¿En qué epoch dejó de mejorar la validación?"])
placeholder()

h("12. Análisis cualitativo", 1)
hint("Las métricas resumen el rendimiento en un número y esconden los errores concretos: mire las predicciones.",
     ["Muestre imágenes concretas en las que el modelo funciona bien y, sobre todo, imágenes en las que falla.",
      "Caracterice QUÉ TIPO de imágenes hacen fallar al modelo: ¿objetos pequeños o lejanos? ¿oclusiones? "
      "¿escenas oscuras o a contraluz? ¿fondos concretos? ¿robots cortados por el borde? ¿desenfoque de movimiento?",
      "Relacione esos fallos con lo que ya sabía de sus datos por el análisis del Bloque 1: ¿estaban esos casos "
      "bien representados en el conjunto de entrenamiento?",
      "Estudie el efecto del umbral de confianza sobre las detecciones mostradas: ¿qué ocurre al subirlo y al "
      "bajarlo? ¿Qué valor elegiría para el robot y por qué?"],
     tips="conectar los errores observados con las limitaciones del conjunto de datos y proponer cómo corregirlos.")
placeholder()
figure_ph("Predicciones sobre el conjunto de test: casos de acierto y casos de fallo.", multi=True)

# ============================================================================
# BLOQUE 3
# ============================================================================
block_divider(3, "Integración y demostración\nsobre el RoboMaster")

hint("Este bloque se completa en la TERCERA entrega, junto con las correcciones de los Bloques 1 y 2.",
     ["No borre estas secciones en las entregas 1 y 2.",
      "La Entrega 3 se cierra con las limitaciones del trabajo y las líneas de mejora.",
      "Todo este bloque se apoya en los scripts de la carpeta week3 y en el modelo entrenado en el Bloque 2."])

# ---------------------------------------------------------------- 12. Modulos
h("13. Módulos del robot", 1)
hint("Extensión orientativa: 1 página. Describa cada módulo del RoboMaster y, sobre todo, PARA QUÉ lo ha usado "
     "en su demo. Recuerde que la demo debe utilizar TODOS los módulos: chasis, torreta (gimbal), cámara, blaster, "
     "LEDs y audio.",
     ["De cada módulo: qué permite hacer y qué papel cumple dentro de su demo.",
      "Preste atención al chasis: explique la diferencia entre moverlo por distancia y por velocidad, y cuál ha "
      "elegido y por qué."])
placeholder()

# ---------------------------------------------------------------- 13. Circuito
h("14. El circuito", 1)
hint("Extensión orientativa: 1 página. Incluya una figura del circuito y explique el recorrido que ha diseñado "
     "sobre ella.",
     ["La figura debe dejar claro: el punto de partida, los obstáculos, los puntos de parada y las posiciones "
      "aproximadas de los robots adversarios. Numere los puntos de parada para poder referirse a ellos en el texto.",
      "Indique cómo ha traducido el recorrido a instrucciones concretas del chasis (distancias, ángulos de giro)."])
placeholder()
figure_ph("Esquema del circuito: recorrido, obstáculos y puntos de parada.")

# ---------------------------------------------------------------- 14. Estrategia
h("15. Estrategia de búsqueda y detección", 1)
hint("Extensión orientativa: 1 página. Explique PASO A PASO qué hace el robot en cada punto de parada, desde que "
     "se detiene hasta que dispara. Es la sección que conecta el Bloque 2 con el robot.",
     ["Descríbala como una secuencia: detenerse, capturar imagen, ejecutar el detector, decidir, girar la torreta, "
      "apuntar, disparar…",
      "La detección es costosa: explique qué hace para no ejecutarla más veces de las necesarias.",
      "Justifique sus decisiones de diseño: ¿dispara solo a la detección de mayor confianza o a todas las que "
      "superen el umbral? ¿Sigue girando la torreta hasta detectar algo o hasta completar los 360 grados? ¿Cada "
      "cuántos grados se detiene a mirar, y por qué ese valor?",
      "¿Qué umbral de confianza ha elegido y por qué? Relaciónelo con lo que observó en el Bloque 2."])
placeholder()

# ---------------------------------------------------------------- 15. Funcionalidades adicionales
h("16. Funcionalidades adicionales", 1)
hint("Extensión orientativa: 2 páginas. Cuente qué ha añadido a la demo por encima de lo exigido y qué aporta.",
     ["Ideas: señalizar con los LEDs el estado del robot (buscando, objetivo detectado, disparando), efectos de "
      "sonido, coreografías, recorridos más complejos, obstáculos extra, gestión de errores…"])
placeholder()

# ---------------------------------------------------------------- 16. Demo final
h("17. La demostración final", 1)
hint("Extensión orientativa: 4 páginas. Es la sección que cierra el proyecto: enseñe QUÉ vio el robot y analice "
     "QUÉ falló y POR QUÉ.",
     ["Incluya las imágenes que guardó el robot en cada punto de parada, con las cajas predichas y su valor de "
      "confianza dibujados encima. Sin esas imágenes esta sección no se puede evaluar.",
      "Comente cada una: ¿detectó lo que debía? ¿Con qué confianza? ¿Disparó a lo correcto?",
      "Analice los fallos uno a uno y explique la causa probable.",
      "Distinga los fallos de percepción (el modelo no vio el robot) de los fallos de ejecución (lo vio, pero "
      "apuntó o se movió mal).",
      "Enlace los fallos con los Bloques 1 y 2: ¿estaban esos casos representados en su conjunto de datos? "
      "¿Los había anticipado el análisis cualitativo del Bloque 2?",
      "Indique cuántos robots consiguió inutilizar y en cuántos intentos."],
     tips="un análisis honesto de los fallos. Una demo imperfecta bien explicada puntúa más que una demo perfecta "
          "sin analizar.")
placeholder()
figure_ph("Imágenes guardadas por el robot en los puntos de parada, con sus detecciones.", multi=True)

# ============================================================================
# CIERRE
# ============================================================================
h("18. Limitaciones y trabajo futuro", 1)
hint("Extensión orientativa: 1 página. Cierre el informe comentando brevemente las limitaciones del trabajo "
     "COMPLETO (Bloques 1-3) y qué haría para mejorarlo.",
     ["Repase los tres bloques y distinga de dónde viene cada limitación: de los datos (cantidad, variedad, "
      "anotación), del modelo (arquitectura, entrenamiento) o de la integración en el robot "
      "(precisión del movimiento, apuntado, tiempo de inferencia).",
      "Para cada limitación, proponga una mejora concreta y realista. Diga cuál cree que tendría más impacto si "
      "solo pudiese abordar una, y por qué."])
placeholder()

page_break()
h("Referencias", 1)
hint("No cuenta para el límite de páginas. Utilice un formato de cita coherente (IEEE, APA…) y cite en el texto.",
     ["Incluya el software utilizado (PyTorch, torchvision, Albumentations, labelImg, RoboMaster SDK…), artículos y documentación consultada.",
      "Si ha empleado herramientas de IA generativa, indíquelo aquí especificando para qué."])
for ref in [
    "[1] Autor(es), «Título», Publicación / URL, año.",
    "[2] […]",
    "[3] […]",
]:
    par = doc.add_paragraph(ref)
    par.paragraph_format.left_indent = Cm(0.8)
    par.paragraph_format.first_line_indent = Cm(-0.8)
    par.paragraph_format.space_after = Pt(4)
    for r in par.runs:
        r.italic = True; r.font.color.rgb = GRIS; r.font.size = Pt(10)

h("Anexos", 1)
hint("Los anexos son CONTENIDO EXTRA: no cuentan para el límite de páginas, pero es posible que no se lean y no "
     "se tendrán en cuenta para la evaluación del proyecto. Todo aquello que quiera que se evalúe debe estar en el "
     "cuerpo del informe.",
     ["Anexo A: tablas extensas de resultados o de parámetros.",
      "Anexo B: figuras adicionales del análisis exploratorio.",
      "Anexo C: fragmentos de código relevantes (solo si son imprescindibles)."])
p("[Opcional]", italic=True, color=GRIS)

doc.save(OUT)
print("Guardado:", OUT)
