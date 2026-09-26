# -*- coding: utf-8 -*-
"""PDF de Cuenta de Cobro — diseño VERTICAL aprobado (15-sep-2026, v2).

Una sola columna, cajas por sección, tabla azul con una fila por cliente,
conceptos por línea (opcional), descuentos como filas propias (SUBTOTAL ->
DESCUENTO -> TOTAL) y valor en letras automático. Cursor estricto: cada
bloque calcula su alto y baja el cursor; verificado sin superposiciones.

v2: la caja DATOS PARA EL PAGO calcula bien su alto (la última línea ya no
queda sobre el borde) y se separó el dibujo de la obtención de datos para
poder generar PREVIEWS sin guardar nada en la base de datos.
"""
import os
from datetime import date

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor
from reportlab.pdfgen import canvas

from .models import Parametro, saludo_de_cliente

# Firma escaneada (se dibuja sobre la línea "Atentamente:"). Se busca relativa a la
# carpeta del proyecto (Recursos/Firma.jpg) para que funcione en P:, Z: o donde se mueva.
_RUTA_FIRMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "Recursos", "Firma.jpg")

AZUL = HexColor("#1F4E79")
AZUL_OSC = HexColor("#17335A")     # tabla: borde/filas (antes GRIS_TABLA)
MORADO = HexColor("#6D28D9")       # acento principal (pedidio de Felipe: PDF en morado lindo)
MORADO_OSC = HexColor("#4C1D95")   # encabezados de tabla/cajas destacadas
GRIS_CLARO = HexColor("#F2F2F2")   # fondo neutro de secciones SIN acento
NEGRO = HexColor("#1a1a1a")
GRIS_TXT = HexColor("#555555")
BORDE = HexColor("#8a8a8a")
BLANCO = HexColor("#ffffff")

W, H = letter  # 612 x 792 vertical
M = 42
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

# ---------------- número a letras ----------------
_UNI = ["", "UN", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE",
        "DIEZ", "ONCE", "DOCE", "TRECE", "CATORCE", "QUINCE", "DIECISÉIS", "DIECISIETE",
        "DIECIOCHO", "DIECINUEVE"]
_DEC = ["", "", "VEINTE", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
_CEN = ["", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS",
        "SEISCIENTOS", "SETECIENTOS", "OCHOCIENTOS", "NOVECIENTOS"]


def _tres(n):
    if n == 100:
        return "CIEN"
    s = []
    c, r = divmod(n, 100)
    if c:
        s.append(_CEN[c])
    if r:
        if r < 20:
            s.append(_UNI[r])
        elif r < 30:
            s.append("VEINTI" + _UNI[r - 20])
        else:
            d, u = divmod(r, 10)
            s.append(_DEC[d] + " Y " + _UNI[u] if u else _DEC[d])
    return " ".join(s)


def numero_a_letras(n):
    n = int(round(n))
    if n == 0:
        return "CERO"
    millones, resto = divmod(n, 1_000_000)
    miles, units = divmod(resto, 1000)
    parts = []
    if millones:
        parts.append("UN MILLÓN" if millones == 1 else _tres(millones) + " MILLONES")
    if miles:
        parts.append("MIL" if miles == 1 else _tres(miles) + " MIL")
    if units:
        parts.append(_tres(units))
    return " ".join(parts)


# ---------------- helpers de dibujo ----------------
def wrap(c, text, font, size, maxw):
    lines, cur = [], ""
    for w in str(text).split():
        t2 = (cur + " " + w).strip()
        if c.stringWidth(t2, font, size) <= maxw:
            cur = t2
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def caja(c, x0, y0, x1, y1, fill=None):
    c.setLineWidth(0.8)
    c.setStrokeColor(BORDE)
    if fill:
        c.setFillColor(fill)
    c.rect(x0, y0, x1 - x0, y1 - y0, stroke=1, fill=1 if fill else 0)


def t(c, x, y, s, size=9, bold=False, color=NEGRO):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(color)
    c.drawString(x, y, s)


def tc(c, cx, y, s, size=9, bold=False, color=NEGRO):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(color)
    c.drawCentredString(cx, y, s)


def tr(c, xr, y, s, size=9, bold=False, color=NEGRO):
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.setFillColor(color)
    c.drawRightString(xr, y, s)


def recortar(c, s, font, size, maxw):
    while c.stringWidth(s, font, size) > maxw and len(s) > 5:
        s = s[:-2].rstrip() + "…"
    return s


def fmt(v):
    return "$ {:,.0f}".format(v)


def _emisor_desde_parametros():
    return {
        "nombre": Parametro.get("emisor_nombre", ""),
        "cc": Parametro.get("emisor_cc", ""),
        "direccion": Parametro.get("emisor_direccion", ""),
        "telefonos": Parametro.get("emisor_telefonos", ""),
    }


def _dibujar(c, d):
    """Dibuja la cuenta con cursor estricto. d = dict de datos (ver _datos_cuenta)."""
    izq, der = M, W - M
    cx = W / 2
    y = H - M
    f = d["fecha"]
    banco = d["banco"]
    emisor = d["emisor"]
    lineas = d["lineas"]
    ajustes = d["ajustes"]
    concepto_default = d["concepto_default"]

    # ---------- 1. Encabezado morado ----------
    hb = 56
    caja(c, izq, y - hb, der, y, fill=MORADO)
    tc(c, cx, y - 24, "CUENTA DE COBRO Nº " + d["numero"], 15, bold=True, color=BLANCO)
    tc(c, cx, y - 43, f"Medellín, {f.day} de {MESES[f.month - 1]} de {f.year}", 9.5, color=BLANCO)
    y -= hb + 16

    # ---------- 2. SEÑOR / SEÑORA / SEÑORES (pagador) ----------
    nb = 58
    caja(c, izq, y - nb, der, y)
    t(c, izq + 10, y - 14, d["pagador_saludo"].upper(), 7, color=GRIS_TXT)
    t(c, izq + 10, y - 31, recortar(c, d["pagador_nombre"], "Helvetica-Bold", 12.5, der - izq - 20), 12.5, bold=True)
    t(c, izq + 10, y - 47, "C. C. o NIT: " + d["pagador_nit"]
      + ("    ·    Ciudad: " + d["pagador_ciudad"] if d["pagador_saludo"] != "Señores" else ""), 9, color=GRIS_TXT)
    y -= nb + 12

    # ---------- 3. DEBE A ----------
    db_ = 56
    caja(c, izq, y - db_, der, y)
    t(c, izq + 10, y - 14, "DEBE A", 7, color=GRIS_TXT)
    t(c, izq + 10, y - 30, emisor["nombre"], 11, bold=True)
    t(c, izq + 10, y - 45, "Dirección y teléfonos: " + emisor["direccion"]
      + "  -  " + emisor["telefonos"], 8.5, color=GRIS_TXT)
    y -= db_ + 12

    # ---------- 4. POR CONCEPTO DE (label arriba, concepto en la línea de abajo) ----------
    con_lines = wrap(c, concepto_default, "Helvetica-Bold", 10.5, der - izq - 24)
    cb = 24 + 14 * len(con_lines)
    caja(c, izq, y - cb, der, y, fill=GRIS_CLARO)
    tc(c, cx, y - 15, "POR CONCEPTO DE:", 9.5, bold=True)
    for i, ln in enumerate(con_lines):
        tc(c, cx, y - 30 - 14 * i, ln, 10.5, bold=True)
    y -= cb + 16

    # ---------- 5. Tabla de valores ----------
    x_div = der - 118
    hh, rh, rh2 = 22, 24, 32
    hay_conceptos = [l for l in lineas if l["concepto"] and l["concepto"] != concepto_default]
    n_rows = sum(rh2 if l in hay_conceptos else rh for l in lineas)
    mostrar_ajustes = bool(ajustes)
    th = hh + n_rows + (rh * (1 + len(ajustes)) if mostrar_ajustes else 0) + rh

    caja(c, izq, y - th, der, y)
    caja(c, izq, y - hh, der, y, fill=MORADO_OSC)
    t(c, izq + 10, y - 15.5, "APELLIDOS Y NOMBRES" + (" / CONCEPTO" if hay_conceptos else ""), 9, bold=True, color=BLANCO)
    tr(c, der - 10, y - 15.5, "VALOR", 9, bold=True, color=BLANCO)
    ry = y - hh
    for l in lineas:
        con_sub = l in hay_conceptos
        r = rh2 if con_sub else rh
        caja(c, izq, ry - r, der, ry)
        c.line(x_div, ry - r, x_div, ry)
        if con_sub:
            t(c, izq + 10, ry - 12, recortar(c, l["nombre"], "Helvetica", 9.5, x_div - izq - 20), 9.5)
            t(c, izq + 10, ry - 26, recortar(c, l["concepto"], "Helvetica", 7.5, x_div - izq - 20), 7.5, color=GRIS_TXT)
            tr(c, x_div + (der - x_div) / 2, ry - 18, fmt(l["valor"]), 9.5)
        else:
            t(c, izq + 10, ry - 16, recortar(c, l["nombre"], "Helvetica", 9.5, x_div - izq - 20), 9.5)
            tr(c, x_div + (der - x_div) / 2, ry - 16, fmt(l["valor"]), 9.5)
        ry -= r
    if mostrar_ajustes:
        caja(c, izq, ry - rh, der, ry, fill=GRIS_CLARO)
        c.line(x_div, ry - rh, x_div, ry)
        t(c, izq + 10, ry - 16, "SUBTOTAL", 9.5)
        tr(c, x_div + (der - x_div) / 2, ry - 16, fmt(sum(l["valor"] for l in lineas)), 9.5)
        ry -= rh
        for aj in ajustes:
            caja(c, izq, ry - rh, der, ry)
            c.line(x_div, ry - rh, x_div, ry)
            t(c, izq + 10, ry - 16, recortar(c, "DESCUENTO — " + aj["motivo"], "Helvetica", 9, x_div - izq - 20), 9, color=GRIS_TXT)
            tr(c, x_div + (der - x_div) / 2, ry - 16, "-" + fmt(abs(aj["valor"])), 9.5, color=GRIS_TXT)
            ry -= rh
    total = sum(l["valor"] for l in lineas) - (sum(a["valor"] for a in ajustes) if mostrar_ajustes else 0)
    caja(c, izq, ry - rh, der, ry, fill=GRIS_CLARO)
    c.line(x_div, ry - rh, x_div, ry)
    t(c, izq + 10, ry - 16.5, "TOTAL A PAGAR", 10, bold=True)
    tr(c, x_div + (der - x_div) / 2, ry - 16.5, fmt(total), 10.5, bold=True)
    y -= th + 12

    # ---------- 6. SON (valor en letras) ----------
    son_txt = numero_a_letras(total) + " PESOS M/CTE."
    son_lines = wrap(c, son_txt, "Helvetica", 9.5, der - izq - 62)
    sb = 13 * len(son_lines) + 14
    caja(c, izq, y - sb, der, y)
    t(c, izq + 10, y - 16, "SON:", 9, bold=True)
    for i, ln in enumerate(son_lines):
        t(c, izq + 48, y - 16 - 13 * i, ln, 9.5)
    y -= sb + 14

    # ---------- 7. Datos para el pago (alto corregido: ninguna línea sale de la caja) ----------
    pb = 14 * len(banco) + 30
    caja(c, izq, y - pb, der, y, fill=GRIS_CLARO)
    t(c, izq + 10, y - 16, "DATOS PARA EL PAGO", 7, bold=True, color=MORADO)
    yy = y - 32
    for l in banco:
        t(c, izq + 10, yy, l, 9)
        yy -= 14
    y -= pb + 14

    # ---------- 8. Observaciones (solo si hay observación para el PDF) ----------
    obs = (d["obs"] or "").strip()
    if obs:
        obs_lines = wrap(c, obs, "Helvetica", 9, der - izq - 60)
        ob = 13 * len(obs_lines) + 16
        caja(c, izq, y - ob, der, y)
        t(c, izq + 10, y - 16, "OBS.:", 9, bold=True)
        for i, ln in enumerate(obs_lines):
            t(c, izq + 52, y - 16 - 13 * i, ln, 9, color=GRIS_TXT)
        y -= ob + 12

    # ---------- 9. Firmas ----------
    # la imagen de firma va SOBRE la línea; reservar su alto para no invadir la caja superior
    sig_h = 0.0
    img = None
    try:
        if os.path.exists(_RUTA_FIRMA):
            from reportlab.lib.utils import ImageReader
            img = ImageReader(_RUTA_FIRMA)
            iw, ih = img.getSize()
            sig_h = 95.0 * ih / iw  # ancho fijo 95pt, alto proporcional
    except Exception:
        img = None
        sig_h = 0.0
    fy = max(90, y - 30 - sig_h)
    if img is not None and y + 14 >= fy + 2 + sig_h:  # solo si cabe sin tocar la caja anterior
        try:
            c.drawImage(img, izq + 20, fy + 2, width=95.0, height=sig_h, mask="auto")
        except Exception:
            pass
    c.setStrokeColor(NEGRO)
    c.setLineWidth(1)
    c.line(izq + 20, fy, W / 2 - 40, fy)
    c.line(W / 2 + 40, fy, der - 20, fy)
    tc(c, (izq + 20 + W / 2 - 40) / 2, fy - 12, "Atentamente:", 9, bold=True)
    tc(c, (izq + 20 + W / 2 - 40) / 2, fy - 25, "C.C. o NIT N°: " + emisor["cc"], 8.5, color=GRIS_TXT)
    tc(c, (W / 2 + 40 + der - 20) / 2, fy - 12, "Aceptada:", 9, bold=True)
    tc(c, (W / 2 + 40 + der - 20) / 2, fy - 25, "C.C. o NIT N°: ____________________", 8.5, color=GRIS_TXT)

    tc(c, cx, 28, "NOTA: Este documento NO es factura de venta.", 7.5, color=GRIS_TXT)


def generar_desde_dict(d, destino):
    """Genera el PDF en `destino` (ruta o BytesIO) a partir del dict de datos."""
    if hasattr(destino, "strip"):
        carpeta = os.path.dirname(destino)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
    c = canvas.Canvas(destino, pagesize=letter)
    _dibujar(c, d)
    c.showPage()
    c.save()
    return destino


def _datos_cuenta(cuenta):
    anio = cuenta.anio
    pagador = cuenta.pagador_principal
    lineas = []
    for lin in cuenta.lineas:
        if lin.estado != "ACTIVA":
            continue
        con = (lin.concepto or "").strip()
        lineas.append({"nombre": lin.cliente.nombre, "concepto": con, "valor": lin.valor})
    ajustes = [{"motivo": a.motivo or "Descuento", "valor": a.valor}
               for a in cuenta.ajustes if a.valor]
    return {
        "numero": cuenta.numero_formateado,
        "fecha": cuenta.fecha or date.today(),
        "pagador_nombre": pagador.nombre if pagador else "",
        "pagador_saludo": saludo_de_cliente(pagador),
        "pagador_nit": pagador.nit_formateado if pagador else "",
        "pagador_ciudad": (pagador.ciudad or "MEDELLÍN") if pagador else "MEDELLÍN",
        "concepto_default": anio.concepto_texto,
        "lineas": lineas,
        "ajustes": ajustes,
        "banco": [l for l in Parametro.get("banco_info", "").split("\n") if l.strip()],
        "emisor": _emisor_desde_parametros(),
        "obs": (cuenta.observaciones or "").strip(),
    }


def datos_preview(a, lineas, pagador, obs=""):
    """Dict de datos para previsualizar SIN crear la cuenta."""
    return {
        "numero": f"{a.prefijo}-{a.numero_siguiente:03d}",
        "fecha": date.today(),
        "pagador_nombre": pagador.nombre if pagador else "",
        "pagador_saludo": saludo_de_cliente(pagador),
        "pagador_nit": pagador.nit_formateado if pagador else "",
        "pagador_ciudad": (pagador.ciudad or "MEDELLÍN") if pagador else "MEDELLÍN",
        "concepto_default": a.concepto_texto,
        "lineas": lineas,
        "ajustes": [],
        "banco": [l for l in Parametro.get("banco_info", "").split("\n") if l.strip()],
        "emisor": _emisor_desde_parametros(),
        "obs": obs,
    }


def generar_pdf(cuenta, ruta):
    generar_desde_dict(_datos_cuenta(cuenta), ruta)
    return ruta


def ruta_pdf(cuenta, carpeta_base):
    """Ruta estándar: <carpeta_base>/<año>/<numero>.pdf"""
    carpeta = os.path.join(carpeta_base, str(cuenta.anio.anio_cobro))
    os.makedirs(carpeta, exist_ok=True)
    return os.path.join(carpeta, f"{cuenta.numero_formateado.replace('-', '_')}.pdf")
