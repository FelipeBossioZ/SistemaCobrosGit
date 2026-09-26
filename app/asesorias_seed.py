# -*- coding: utf-8 -*-
"""Catálogo estándar de asesorías de la oficina (Fase B + motor + bases 26/09).
Se siembra una sola vez; después se edita desde Parámetros → Asesorías.
es_fija: True  = tarifa fija (subtotal = valor x cantidad)
         False = porcentaje de la renta base (subtotal = pct% x renta_base)
Bases aprobadas por Felipe (26/09): IVA 150.000, Consumo 100.000,
Anticipo RST 100.000, Retefuente 100.000, Contabilidad PN 600.000/mes.
Otras asesorías es la única libre.
"""

# orden, código, nombre, tipo, %, valor fijo, base, es_fija
ASESORIAS = [
    (10,  "RENTA",        "Renta",                    "TODOS", 100, 0,      "",                              False),
    (15,  "RST_SIMPLE",   "RST (Simple)",             "TODOS", 100, 0,      "trata como renta",              False),
    (20,  "IP",           "Impuesto de patrimonio",   "TODOS",  50, 0,      "",                              False),
    (30,  "EXOGENA",      "Exógena",                  "TODOS",  75, 0,      "",                              False),
    (40,  "EXO_MPIO",     "Exógena municipio",        "TODOS",  15, 0,      "",                              False),
    (50,  "F2516",        "Formato 2516",             "TODOS",  10, 0,      "conservar 10% / presentar 20%", False),
    (60,  "ACT_EXT",      "Activos en el exterior",   "TODOS",  30, 0,      "",                              False),
    (70,  "CAMARA",       "Cámara de comercio",       "TODOS",  50, 0,      "",                              False),
    (75,  "ICA",          "ICA (declaración anual)",  "TODOS",  50, 0,      "",                              False),
    (95,  "RUB",          "RUB",                      "TODOS",  15, 0,      "",                              False),
    (97,  "SUPERSOC",     "Supersociedades",          "TODOS",  75, 0,      "",                              False),
    (80,  "IVA",          "IVA",                      "TODOS",   0, 150000, "base $150.000",                 True),
    (85,  "CONSUMO",      "Impuesto al consumo",      "TODOS",   0, 100000, "base $100.000",                 True),
    (87,  "ANTICIPO_RST", "Anticipo RST",             "TODOS",   0, 100000, "base $100.000",                 True),
    (90,  "RF",           "Retefuente",               "TODOS",   0, 100000, "base $100.000",                 True),
    (100, "DEV",          "Devoluciones",             "TODOS",  20, 0,      "",                              False),
    (110, "FE_INS",       "FE inscripción",           "TODOS",   0, 80000,  "anual + IPC",                   True),
    (120, "FE_FAC",       "FE por factura",           "TODOS",   0, 20000,  "por factura",                   True),
    (130, "CONT_PN",      "Contabilidad PN",          "PN",      0, 600000, "tarifa mensual",                True),
    (140, "CONT_PJ_B",    "Contabilidad PJ básica",   "PJ",      0, 600000, "por mes",                       True),
    (150, "CONT_PJ_C",    "Contabilidad PJ compleja", "PJ",      0, 0,      "1 SMLV / mes",                  True),
    (990, "OTRAS",        "Otras asesorías",          "TODOS",   0, 0,      "valor libre",                   True),
]

# bases aprobadas 26/09: se siembran UNA VEZ en BDs viejas (solo si el valor esta en 0)
SINCRONIZAR_BASES = {
    "IVA": 150000,
    "CONSUMO": 100000,
    "ANTICIPO_RST": 100000,
    "RF": 100000,
    "CONT_PN": 600000,
}


def seed_asesorias():
    """Inserta los códigos que falten, sincroniza es_fija y siembra las bases
    aprobadas cuando el valor guardado sigue en 0 (no pisa ediciones del usuario)."""
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
    for cod, fila in existentes.items():
        if cod in por_codigo and bool(fila.es_fija) != por_codigo[cod][7]:
            fila.es_fija = por_codigo[cod][7]
    sembradas = []
    for cod, base_ in SINCRONIZAR_BASES.items():
        fila = existentes.get(cod)
        if fila and not (fila.defecto_valor or 0):
            fila.defecto_valor = float(base_)
            if cod == "CONT_PN" and (fila.base_min or "").strip() == "1 SMLV / mes":
                fila.base_min = "tarifa mensual"
            sembradas.append(cod)
    if nuevos or sembradas or db.session.dirty:
        db.session.commit()
    return nuevos, sembradas
