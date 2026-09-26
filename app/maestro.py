# -*- coding: utf-8 -*-
"""Lectura del Sistema Maestro para el motor de asesorias (solo lectura).

Mapeo impuesto maestro -> codigo del catalogo (MAPA). "RST" del maestro se
trata como renta (decision Felipe 26/09: RST_SIMPLE presentada = renta OK).
"Presentado" = scanner_estado PRESENTADA o PAGADA (o con scanner_archivo).
Ano de cobro activo (ciclo gravable->cobro):
  - anuales (renta, exogena, camara...): periodo "AG-<gravable>" (ej AG-2025)
  - periodicos (IVA, RF, CONSUMO, ANTICIPO_RST): periodo que empieza con "<anio_cobro>"
"""
import os
import sqlite3

MAPA = {
    "RENTA":        ("RENTA_PN", "RENTA_PJ"),
    "RST_SIMPLE":   ("RST",),
    "IP":           ("PATRIMONIO",),
    "EXOGENA":      ("EXOGENA",),
    "EXO_MPIO":     ("EXG_MED",),
    "F2516":        ("FORMATO_2516", "FORMATO_2517"),
    "ACT_EXT":      ("ACTIVOS_EXTERIOR",),
    "CAMARA":       ("REGISTRO_MERCANTIL",),
    "ICA":          ("ICA",),
    "RUB":          ("RUB",),
    "SUPERSOC":     ("SUPERSOCIEDADES",),
    "IVA":          ("IVA",),
    "RF":           ("RETEFUENTE",),
    "CONSUMO":      ("CONSUMO",),
    "ANTICIPO_RST": ("ANTICIPO_RST",),
}
PERIODICOS = ("IVA", "RF", "CONSUMO", "ANTICIPO_RST", "CAMARA")


def bd_maestro():
    """Ruta de la BD del maestro activa (via parametros/rutas_comunes)."""
    from .routes import _ruta_maestro_activa
    ruta = _ruta_maestro_activa()
    if not ruta or not os.path.isdir(ruta):
        return None
    bd = os.path.join(ruta, "data", "sistema_maestro_v4.db")
    return bd if os.path.isfile(bd) else None


def _presentado(estado, archivo):
    return (estado or "").strip() in ("PRESENTADA", "PAGADA") or bool((archivo or "").strip())


def leer_maestro(anio_cobro, anio_gravable, nits):
    """{nit: {codigo_catalogo: (cantidad, [estados])}} solo con lo presentado.
    nits: conjunto de NITs (strings limpios) a considerar. None si no hay BD."""
    bd = bd_maestro()
    if not bd:
        return None
    anual = "AG-%d" % anio_gravable
    prefijo_per = "%d" % anio_cobro
    res = {}
    con = sqlite3.connect(bd)
    try:
        filas = con.execute(
            "SELECT nit, impuesto, periodo, scanner_estado, scanner_archivo "
            "FROM obligaciones WHERE nit IS NOT NULL").fetchall()
    finally:
        con.close()
    for nit, impuesto, periodo, estado, archivo in filas:
        n = (nit or "").strip()
        if not n or n not in nits:
            continue
        if not _presentado(estado, archivo):
            continue
        por_nit = res.setdefault(n, {})
        for cod, imps in MAPA.items():
            if impuesto not in imps:
                continue
            if cod in PERIODICOS:
                if not (periodo or "").startswith(prefijo_per):
                    continue
                dato = por_nit.get(cod) or (0, [])
                por_nit[cod] = (dato[0] + 1, dato[1])
            else:
                per = (periodo or "").strip()
                if per in (anual, "AG-%d" % anio_cobro):
                    ok = _presentado(estado, archivo)
                elif per == "":
                    ok = (estado or "").strip() in ("PRESENTADA", "PAGADA")
                else:
                    ok = False
                if not ok:
                    continue
                dato = por_nit.get(cod) or (0, [])
                por_nit[cod] = (dato[0], dato[1] + [estado or "PRESENTADA"])
    return res
