# -*- coding: utf-8 -*-
"""Cat\u00e1logo est\u00e1ndar de asesor\u00edas de la oficina (Fase B + motor).
Se siembra una sola vez; despu\u00e9s se edita desde Par\u00e1metros \u2192 Asesor\u00edas.
es_fija: True  = tarifa fija (subtotal = valor x cantidad)
         False = porcentaje de la renta base (subtotal = pct% x renta_base)
"""

# orden, c\u00f3digo, nombre, tipo, %, valor fijo, base, es_fija
ASESORIAS = [
    (10,  "RENTA",        "Renta",                    "TODOS", 100, 0,      "",                              False),
    (15,  "RST_SIMPLE",   "RST (Simple)",             "TODOS", 100, 0,      "trata como renta",              False),
    (20,  "IP",           "Impuesto de patrimonio",   "TODOS",  50, 0,      "",                              False),
    (30,  "EXOGENA",      "Ex\u00f3gena",                  "TODOS",  75, 0,      "",                              False),
    (40,  "EXO_MPIO",     "Ex\u00f3gena municipio",         "TODOS",  15, 0,      "",                              False),
    (50,  "F2516",        "Formato 2516",             "TODOS",  10, 0,      "conservar 10% / presentar 20%", False),
    (60,  "ACT_EXT",      "Activos en el exterior",   "TODOS",  30, 0,      "",                              False),
    (70,  "CAMARA",       "C\u00e1mara de comercio",        "TODOS",  50, 0,      "",                              False),
    (75,  "ICA",          "ICA (declaraci\u00f3n anual)",   "TODOS",  50, 0,      "",                              False),
    (95,  "RUB",          "RUB",                      "TODOS",  15, 0,      "",                              False),
    (97,  "SUPERSOC",     "Supersociedades",          "TODOS",  75, 0,      "",                              False),
    (80,  "IVA",          "IVA",                      "TODOS",   0, 0,      "base $150.000",                 True),
    (85,  "CONSUMO",      "Impuesto al consumo",      "TODOS",   0, 0,      "base retefuente $100.000",      True),
    (87,  "ANTICIPO_RST", "Anticipo RST",             "TODOS",   0, 0,      "base retefuente $100.000",      True),
    (90,  "RF",           "Retefuente",               "TODOS",   0, 0,      "base $100.000",                 True),
    (100, "DEV",          "Devoluciones",             "TODOS",  20, 0,      "",                              False),
    (110, "FE_INS",       "FE inscripci\u00f3n",            "TODOS",   0, 80000,  "anual + IPC",                   True),
    (120, "FE_FAC",       "FE por factura",           "TODOS",   0, 20000,  "por factura",                   True),
    (130, "CONT_PN",      "Contabilidad PN",          "PN",      0, 0,      "1 SMLV / mes",                  True),
    (140, "CONT_PJ_B",    "Contabilidad PJ b\u00e1sica",    "PJ",      0, 600000, "por mes",                       True),
    (150, "CONT_PJ_C",    "Contabilidad PJ compleja", "PJ",      0, 0,      "1 SMLV / mes",                  True),
    (990, "OTRAS",        "Otras asesor\u00edas",            "TODOS",   0, 0,      "valor libre",                   True),
]


def seed_asesorias():
    """Inserta los c\u00f3digos que falten y sincroniza es_fija (no toca % ni valores editados)."""
    from app.models import db, AsesoriaCatalogo
    por_codigo = {a[1]: a for a in ASESORIAS}
    existentes = {a.codigo: a for a in AsesoriaCatalogo.query.all()}
    nuevos = 0
    for orden, cod, nom, tipo, pct, valor, base_, es_fija in ASESORIAS:
        if cod in existentes:
            continue
        db.session.add(AsesoriaCatalogo(orden=orden, codigo=cod, nombre=nom,
                                        tipo=tipo, defecto_pct=pct,
                                        defecto_valor=valor, base_min=base_,
                                        es_fija=es_fija, activo=True))
        nuevos += 1
    # sincronizar es_fija en los que ya existian (columna nueva, sin ediciones)
    for cod, fila in existentes.items():
        if cod in por_codigo and bool(fila.es_fija) != por_codigo[cod][7]:
            fila.es_fija = por_codigo[cod][7]
    if nuevos or db.session.dirty:
        db.session.commit()
    return nuevos
