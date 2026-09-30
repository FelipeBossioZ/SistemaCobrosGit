# -*- coding: utf-8 -*-
"""Generador de imagen PNG de una cuenta de cobro (para enviar por WhatsApp).

Orden de preferencia:
1. pymupdf (fitz) si está instalado -> rasteriza el PDF vectorial (calidad alta)
2. pdf2image + Poppler si está disponible
3. Pillow dibuja la lámina directamente (sin dependencias externas)
"""
import os

from .models import CuentaCobro
from .pdf_generator import generar_desde_dict, _datos_cuenta

ANCHO = 1000          # px; WhatsApp lo recomprime igual, este ancho es legible
ESCALA = 150.0 / 72.0  # 150 dpi sobre puntos del PDF


def _render_con_fitz(ruta_pdf, ruta_png):
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf   # versiones viejas
    doc = pymupdf.open(ruta_pdf)
    try:
        pagina = doc[0]
        pix = pagina.get_pixmap(matrix=pymupdf.Matrix(ESCALA, ESCALA), alpha=False)
        pix.save(ruta_png)
    finally:
        doc.close()
    return ruta_png


def _render_con_pdf2image(ruta_pdf, ruta_png):
    from pdf2image import convert_from_path
    imgs = convert_from_path(ruta_pdf, dpi=150)
    imgs[0].save(ruta_png, "PNG")
    return ruta_png


def _render_con_pillow(cuenta, ruta_png):
    """Lámina dibujada directamente (sin Poppler/pymupdf). Vertical, estilo WhatsApp.
    Anti-cortes: los textos largos se parten en varias líneas, la fuente se encoge
    si una línea no cabe y el lienzo crece en altura; ninguna línea se sale jamás
    por la derecha."""
    from PIL import Image, ImageDraw, ImageFont

    d = _datos_cuenta(cuenta)
    W = 1000
    M = 56            # margen
    MORADO = (74, 44, 114)
    LILA = (243, 239, 250)
    GRIS = (110, 110, 110)
    NEGRO = (33, 33, 33)
    ANCHO_UT = W - 2 * M - 16   # ancho útil para líneas con sangría

    _tmp = ImageDraw.Draw(Image.new("RGB", (8, 8)))

    def fuente(tam, negrita=False):
        nombres = ["arialbd.ttf" if negrita else "arial.ttf",
                   "segoeuib.ttf" if negrita else "segoeui.ttf",
                   "calibrib.ttf" if negrita else "calibri.ttf"]
        for n in nombres:
            try:
                return ImageFont.truetype(n, tam)
            except OSError:
                continue
        return ImageFont.load_default()

    def _una(texto, tam, negrita=False, ancho=W - 2 * M):
        """Devuelve la fuente encogida hasta que el texto quepa en UNA línea."""
        tam = int(tam)
        f = fuente(tam, negrita)
        while tam > 14 and _tmp.textlength(texto, font=f) > ancho:
            tam -= 2
            f = fuente(tam, negrita)
        return f

    def _envuelto(texto, tam, negrita=False, ancho=ANCHO_UT):
        """Devuelve (fuente, líneas) con ajuste de palabra; encoge hasta que
        TODAS las líneas quepan en el ancho útil."""
        tam = int(tam)
        while tam >= 14:
            f = fuente(tam, negrita)
            lineas, actual = [], ""
            for p in (texto or "").split():
                prueba = (actual + " " + p).strip()
                if _tmp.textlength(prueba, font=f) <= ancho:
                    actual = prueba
                else:
                    if actual:
                        lineas.append(actual)
                    actual = p
            lineas.append(actual or "")
            if all(_tmp.textlength(l, font=f) <= ancho for l in lineas):
                return f, lineas
            tam -= 2
        return fuente(14, negrita), [texto or ""]

    img = Image.new("RGB", (W, 2600), "white")
    dr = ImageDraw.Draw(img)

    # ---- banda superior morada ----
    dr.rectangle([0, 0, W, 130], fill=MORADO)
    em = d.get("emisor", {})
    dr.text((M, 26), em.get("nombre", ""),
            font=_una(em.get("nombre", ""), 40, True), fill="white")
    linea_id = " · ".join(x for x in [em.get("cc", ""), em.get("telefonos", "")] if x)
    if linea_id:
        dr.text((M, 86), linea_id, font=_una(linea_id, 18), fill=(230, 224, 240))
    y = 160

    f_h2 = fuente(26, True)
    f_txt = fuente(22)
    AL = 30          # alto de línea de texto normal

    dr.text((M, y), d.get("titulo", "CUENTA DE COBRO"), font=f_h2, fill=MORADO)
    y += 44
    ft, lin = _envuelto(d.get("numero", ""), 22)
    for l in lin:
        dr.text((M, y), l, font=ft, fill=NEGRO)
        y += AL
    y += 10

    dr.text((M, y), "Cliente(s):", font=f_txt, fill=GRIS)
    y += 32
    for ln in d.get("lineas", []):
        fc, lin = _envuelto(ln.get("nombre", ""), 22)
        for l in lin:
            dr.text((M + 16, y), l, font=fc, fill=NEGRO)
            y += AL
    y += 10

    dr.text((M, y), "Concepto:", font=f_txt, fill=GRIS)
    y += 32
    fc, lin = _envuelto((d.get("concepto_default", "") or "").replace("\n", " "), 22)
    for l in lin:
        dr.text((M + 16, y), l, font=fc, fill=NEGRO)
        y += AL
    y += 10

    # ---- total destacado ----
    total = sum(float(ln.get("valor") or 0) for ln in d.get("lineas", [])) \
        - sum(float(a.get("valor") or 0) for a in d.get("ajustes", []))
    total = f"${total:,.0f}".replace(",", ".")
    f_tot = _una(total, 26, True, W - 2 * M - 260)
    dr.rectangle([M, y, W - M, y + 64], fill=LILA)
    dr.text((M + 16, y + 16), "TOTAL A PAGAR:", font=f_h2, fill=MORADO)
    w_tot = _tmp.textlength(total, font=f_tot)
    dr.text((W - M - 16 - w_tot, y + 16), total, font=f_tot, fill=MORADO)
    y += 92

    banco = "\n".join(d.get("banco", []) or []).strip()
    if banco:
        dr.text((M, y), "Se puede consignar o Transferir en:", font=f_txt, fill=GRIS)
        y += 34
        for linea in banco.split("\n"):
            if not linea.strip():
                y += 12
                continue
            fb, lin = _envuelto(linea, 22, False, ANCHO_UT)
            for l in lin:
                dr.text((M + 16, y), l, font=fb, fill=NEGRO)
                y += AL
        y += 8

    firma = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "Recursos", "Firma.jpg")
    if os.path.isfile(firma):
        try:
            fimg = Image.open(firma)
            alto_f = 90
            ancho_f = int(fimg.width * alto_f / fimg.height)
            fimg = fimg.resize((ancho_f, alto_f))
            img.paste(fimg, (W - M - ancho_f, y + 10), fimg if fimg.mode == "RGBA" else None)
        except OSError:
            pass
    dr.text((W - M - 300, y + 104), em.get("nombre", ""),
            font=_una(em.get("nombre", ""), 18, False, 300), fill=GRIS)
    y += 140

    img = img.crop((0, 0, W, min(y + M, img.height)))
    img.save(ruta_png, "PNG")
    return ruta_png


def generar_imagen(cuenta: CuentaCobro, ruta_png: str) -> str:
    """Imagen PNG de la cuenta. Primero intenta rasterizar el PDF real (misma
    apariencia del documento); si no hay rasterizador, dibuja una lámina."""
    carpeta = os.path.dirname(ruta_png)
    os.makedirs(carpeta, exist_ok=True)
    ruta_pdf_tmp = os.path.splitext(ruta_png)[0] + ".pdf"
    try:
        generar_desde_dict(_datos_cuenta(cuenta), ruta_pdf_tmp)
        try:
            return _render_con_fitz(ruta_pdf_tmp, ruta_png)
        except ImportError:
            pass
        try:
            return _render_con_pdf2image(ruta_pdf_tmp, ruta_png)
        except Exception:
            pass
    finally:
        try:
            if os.path.isfile(ruta_pdf_tmp):
                os.remove(ruta_pdf_tmp)
        except OSError:
            pass
    return _render_con_pillow(cuenta, ruta_png)


def _nombre_imagen(cuenta: CuentaCobro) -> str:
    from .routes import _nombre_pdf
    return os.path.splitext(_nombre_pdf(cuenta))[0] + ".png"
