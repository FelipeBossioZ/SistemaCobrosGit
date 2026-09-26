# -*- coding: utf-8 -*-
"""Catálogo estándar de asesorías de la oficina (Fase B).
Se siembra una sola vez; después se edita desde Parámetros → Asesorías."""

ASESORIAS = [
    # orden, código, nombre, tipo, %, valor fijo, base
    (10, "RENTA",      "Renta",                    "TODOS", 100, 0,      ""),
    (20, "IP",         "Impuesto de patrimonio",   "TODOS",  50, 0,      ""),
    (30, "EXOGENA",    "Exógena",                  "TODOS",  75, 0,      ""),
    (40, "EXO_MPIO",   "Exógena municipio",        "TODOS",  15, 0,      ""),
    (50, "F2516",      "Formato 2516",             "TODOS",  10, 0,      "conservar 10% / presentar 20%"),
    (60, "ACT_EXT",    "Activos en el exterior",   "TODOS",  30, 0,      ""),
    (70, "CAMARA",     "Cámara de comercio",       "TODOS",  50, 0,      ""),
    (80, "IVA",        "IVA",                      "TODOS",   0, 0,      "base $150.000"),
    (90, "RF",         "Retefuente",               "TODOS",   0, 0,      "base $100.000"),
    (100, "DEV",       "Devoluciones",             "TODOS",  20, 0,      ""),
    (110, "FE_INS",    "FE inscripción",           "TODOS",   0, 80000,  "anual + IPC"),
    (120, "FE_FAC",    "FE por factura",           "TODOS",   0, 20000,  "por factura"),
    (130, "CONT_PN",   "Contabilidad PN",          "PN",      0, 0,      "1 SMLV / mes"),
    (140, "CONT_PJ_B", "Contabilidad PJ básica",   "PJ",      0, 600000, "por mes"),
    (150, "CONT_PJ_C", "Contabilidad PJ compleja", "PJ",      0, 0,      "1 SMLV / mes"),
    (990, "OTRAS",     "Otras asesorías",          "TODOS",   0, 0,      "valor libre"),
]


def seed_asesorias():
    """Inserta el catálogo una sola vez (no toca nada existente)."""
    from app.models import db, AsesoriaCatalogo
    existentes = {a.codigo for a in AsesoriaCatalogo.query.all()}
    nuevos = 0
    for orden, cod, nom, tipo, pct, valor, base_ in ASESORIAS:
        if cod in existentes:
            continue
        db.session.add(AsesoriaCatalogo(orden=orden, codigo=cod, nombre=nom,
                                        tipo=tipo, defecto_pct=pct,
                                        defecto_valor=valor, base_min=base_,
                                        activo=True))
        nuevos += 1
    if nuevos:
        db.session.commit()
    return nuevos
