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
    """Lámina dibujada directamente (sin Poppler/pymupdf). Vertical, estilo WhatsApp."""
    from PIL import Image, ImageDraw, ImageFont

    d = _datos_cuenta(cuenta)
    W = 1000
    M = 56            # margen
    MORADO = (74, 44, 114)
    GRIS = (110, 110, 110)
    NEGRO = (33, 33, 33)

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

    f_titulo = fuente(40, True)
    f_h2 = fuente(26, True)
    f_txt = fuente(22)
    f_peq = fuente(18)

    # altura estimada por bloques: se dibuja con cursor y la imagen se recorta al final
    img = Image.new("RGB", (W, 1900), "white")
    dr = ImageDraw.Draw(img)
    y = M

    # banda superior morada
    dr.rectangle([0, 0, W, 130], fill=MORADO)
    y = 34
    emisor = d.get("emisor_nombre", "")
    dr.text((M, y), emisor, font=f_titulo, fill="white")
    y += 52
    linea_id = " · ".join(x for x in [d.get("emisor_cc", ""), d.get("emisor_telefonos", "")] if x)
    if linea_id:
        dr.text((M, y), linea_id, font=f_peq, fill=(230, 224, 240))
    y = 160

    dr.text((M, y), d.get("titulo", "CUENTA DE COBRO"), font=f_h2, fill=MORADO)
    y += 44
    dr.text((M, y), d.get("numero", ""), font=f_txt, fill=NEGRO)
    y += 36

    dr.text((M, y), "Señor" if False else "Cliente(es):", font=f_txt, fill=GRIS)
    y += 32
    for cli in d.get("clientes", []):
        dr.text((M + 16, y), cli, font=f_txt, fill=NEGRO)
        y += 30
    y += 10

    dr.text((M, y), "Concepto:", font=f_txt, fill=GRIS)
    y += 32
    for linea in (d.get("concepto", "") or "").split("\n"):
        dr.text((M + 16, y), linea, font=f_txt, fill=NEGRO)
        y += 30
    y += 10

    # total destacado
    dr.rectangle([M, y, W - M, y + 64], fill=(243, 239, 250))
    dr.text((M + 16, y + 16), "TOTAL A PAGAR:", font=f_h2, fill=MORADO)
    total = d.get("total", "")
    w_tot = dr.textlength(str(total), font=f_h2)
    dr.text((W - M - 16 - w_tot, y + 16), str(total), font=f_h2, fill=MORADO)
    y += 92

    banco = (d.get("banco_info", "") or "").strip()
    if banco:
        dr.text((M, y), "Se puede consignar o Transferir en:", font=f_txt, fill=GRIS)
        y += 34
        for linea in banco.split("\n"):
            dr.text((M + 16, y), linea, font=f_txt, fill=NEGRO)
            y += 30
        y += 8

    firma = d.get("firma")
    if firma and os.path.isfile(firma):
        try:
            fimg = Image.open(firma)
            alto_f = 90
            ancho_f = int(fimg.width * alto_f / fimg.height)
            fimg = fimg.resize((ancho_f, alto_f))
            img.paste(fimg, (W - M - ancho_f, y + 10), fimg if fimg.mode == "RGBA" else None)
        except OSError:
            pass
    dr.text((W - M - 230, y + 104), d.get("emisor_nombre", ""), font=f_peq, fill=GRIS)
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
