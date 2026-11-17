# -*- coding: utf-8 -*-
"""FASE 2A - Importador de FACTURACION desde el Excel 'Presupuesto de cobros AG
2025 -Facturacion.xlsx'.

Universo FACT (independiente del universo CDEC):
- Clientes: hoja 'Facturas' (29 PN + 19 PJ) + sociedades pagadoras que solo
  aparecen en 'Grupos Facturacion' (LINABI, TRULY, ECHAVARRIA ABOGADOS, SAN MARDO).
- Grupos de factura: hoja 'Grupos Facturacion' (bloque de codigos r10+ y detalle
  de miembros). Cada grupo = UNA factura a nombre del pagador.
- Presupuestos AG-2025 iniciales: lo EFECTIVAMENTE COBRADO en AG-2024
  (columna 'VALOR REAL COBRADO' del bloque de codigos, prorrateado entre los
  miembros por el valor de su linea) x IPC (5.10%), redondeado a centenas.
- Retencion: flag por cliente importado de 'AGENTE RETENEDOR' (S/NO).
  Reglas: RF la practica siempre el comprador al 11%, EXCEPTO clientes en RST
  y personas naturales no obligadas (no comerciantes) -> rf_activa=False.

Idempotente: si el cliente ya existe (por codigo o nombre) solo actualiza
seccion/retencion y crea lo que falte (grupos, presupuestos, miembros).
"""
import re
from datetime import date

import openpyxl

from .models import db, Cliente, GrupoFamiliar, PresupuestoCliente, AnioCobro

IPC_FACT = 0.051  # IPC para presupuesto inicial AG-2025

# Sociedades pagadoras sin linea propia (solo encabezan la factura de su grupo)
# El nombre debe coincidir con la hoja 'Grupos Facturacion'.
SOCIEDADES_SIN_LINEA = ("LINABI SAS", "TRULY NOLEN DE COLOMBIA SAS",
                        "ECHAVARRÍA ABOGADOS SAS", "SAN MARDO SAS")

# Empresas con #N/A en el bloque de codigos: no se importan (sin datos).
EMPRESAS_OMITIDAS = ("DIRAC CORE SAS", "UNBOUND WELLNESS SAS", "SUPER CAMPEROS SAS")


def _txt(v):
    return "" if v is None else str(v).strip()


def _norm(nombre):
    """Normaliza un nombre para emparejar: mayusculas, un solo espacio,
    S A S -> SAS y sin 'EN LIQUIDACION' (el Excel mezcla ambas formas)."""
    s = _txt(nombre).upper()
    s = s.replace("S. A. S.", "SAS").replace("S. A. S", "SAS").replace("S.A.S.", "SAS")
    s = s.replace("S A S", "SAS").replace("S.A.S", "SAS")
    s = s.replace("EN LIQUIDACI\u00d3N", "").replace("EN LIQUIDACION", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _es_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def leer_excel(path):
    """Lee las hojas necesarias y devuelve un dict con todo el universo FACT.

    {
      "clientes": [{codigo, nombre, nit, dv, tipo, rf_excel, valor_linea, obs}],
      "bloque_grupos": [{codigo, nombre, valor_final, cobrado_real}],
      "grupos": [{codigo, nombre, miembros: [nombre...]}],
      "codigos_base": {nombre_normalizado: codigo},   # hoja 'Códigos'
    }
    """
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except PermissionError:
        # abierto en Excel: leer una copia temporal
        import os, shutil, tempfile
        tmp = os.path.join(tempfile.gettempdir(), "fact_leer.xlsx")
        shutil.copy2(path, tmp)
        wb = openpyxl.load_workbook(tmp, data_only=True, read_only=True)

    # ---------- hoja 'Facturas': clientes del universo FACT ----------
    clientes = []
    ws = wb["Facturas"]
    for i, row in enumerate(ws.iter_rows(min_row=9, max_row=37, max_col=20, values_only=True), 9):
        if _es_num(row[0]) and _txt(row[1]):
            clientes.append({"nombre": _txt(row[1]), "codigo": int(row[2]),
                             "nit": _txt(row[3]), "dv": _txt(row[4]),
                             "tipo": "PN", "rf_excel": _txt(row[7]).upper().startswith("S"),
                             "valor_linea": _num(row[5]), "obs": _txt(row[19])})
    for i, row in enumerate(ws.iter_rows(min_row=54, max_row=75, max_col=20, values_only=True), 54):
        if _es_num(row[0]) and _txt(row[1]):
            clientes.append({"nombre": _txt(row[1]), "codigo": int(row[2]),
                             "nit": _txt(row[3]), "dv": _txt(row[4]),
                             "tipo": "PJ", "rf_excel": _txt(row[7]).upper().startswith("S"),
                             "valor_linea": _num(row[5]), "obs": _txt(row[19])})

    # ---------- hoja 'Grupos Facturacion': bloque de codigos + detalle ----------
    ws = wb["Grupos Facturación"]
    bloque = {}   # codigo_grupo -> {nombre, valor_final, cobrado_real}
    for row in ws.iter_rows(min_row=10, max_row=40, max_col=6, values_only=True):
        cod = _txt(row[0])
        nom = _txt(row[1])
        if not cod or not nom or cod in ("CÓDIGO", "CÃ“DIGO"):
            continue
        if nom.upper() in EMPRESAS_OMITIDAS:
            continue
        bloque[cod] = {"nombre": nom, "valor_final": _num(row[2]),
                       "cobrado_real": _num(row[5])}

    # detalle: r43+ -> encabezados de grupo (c1 numerico, c3 vacio),
    # miembros (c1 numerico + c3 numerico), cierre (c1 = codigo corto)
    grupos = []
    actual = None
    for row in ws.iter_rows(min_row=43, max_row=ws.max_row, max_col=7, values_only=True):
        c1, c2, c3 = row[0], _txt(row[1]), row[2]
        if not c2:
            continue
        if _es_num(c1) and not _es_num(c3) and _num(c3) == 0 and not bloque.get(_txt(c1)):
            # encabezado de grupo: fila con numero y sin valores
            actual = {"codigo": None, "nombre": c2, "miembros": []}
            grupos.append(actual)
            continue
        if not _es_num(c1) and _txt(c1):
            # cierre del grupo: celda codigo corto (CAMP, TRLY...)
            cod = _txt(c1)
            if actual is not None and cod in bloque:
                actual["codigo"] = cod
            continue
        # miembro: c1 numerico (o vacio) + valor en c3
        if actual is not None and _es_num(c3):
            actual["miembros"].append(c2)
    # quitar grupos sin codigo en el bloque (encabezados sueltos)
    grupos = [g for g in grupos if g["codigo"]]
    # los grupos de un solo nombre que tambien son el pagador: quedan igual

    # ---------- hoja 'Códigos': codigo oficial por nombre (para sociedades sin linea) ----------
    codigos_base = {}
    ws = wb["Códigos"]
    for row in ws.iter_rows(min_row=8, max_row=ws.max_row, max_col=3, values_only=True):
        nom = _txt(row[1])
        if nom and _es_num(row[0]):
            codigos_base[_norm(nom)] = int(row[0])

    wb.close()
    return {"clientes": clientes, "bloque_grupos": bloque,
            "grupos": grupos, "codigos_base": codigos_base}


def _cobrado_real_por_cliente(data):
    """Prorratea el cobrado real de cada grupo entre sus miembros por valor de linea.
    Devuelve {nombre_normalizado: cobrado_real}."""
    por_nombre = {}
    lineas = {c["nombre"]: c["valor_linea"] for c in data["clientes"]}
    for g in data["grupos"]:
        b = data["bloque_grupos"].get(g["codigo"])
        if not b:
            continue
        cobrado = b["cobrado_real"] or 0
        if cobrado <= 0:
            continue
        vals = [(m, lineas.get(m, 0.0)) for m in g["miembros"]]
        total = sum(v for _, v in vals)
        if total <= 0:
            parte = cobrado / max(len(vals), 1)
            for m, _ in vals:
                por_nombre[_norm(m)] = por_nombre.get(_norm(m), 0.0) + parte
            continue
        for m, v in vals:
            p = cobrado * (v / total)
            if p:
                por_nombre[_norm(m)] = por_nombre.get(_norm(m), 0.0) + p
    return por_nombre


def _siguiente_codigo(bd_codigos, codigos_base, nombre):
    """Codigo para sociedades sin linea: usa la hoja 'Códigos' si esta libre;
    si no, el maximo disponible + 1. bd_codigos se actualiza en cada llamada
    para que varias sociedades nuevas nunca compartan codigo."""
    cod = codigos_base.get(_norm(nombre))
    if cod and cod not in bd_codigos:
        bd_codigos.add(cod)
        return cod
    nuevo = max(bd_codigos or {0}) + 1
    bd_codigos.add(nuevo)
    return nuevo


def previsualizar(path):
    """Lee el Excel y devuelve el plan completo SIN tocar la BD (dry-run)."""
    data = leer_excel(path)
    cobrado = _cobrado_real_por_cliente(data)
    nombres_cli = {_norm(c["nombre"]): c for c in data["clientes"]}
    a = AnioCobro.query.filter_by(activo=True).first()
    anio = a.anio_cobro if a else None
    ipc = IPC_FACT

    bd_codigos = {c.codigo for c in Cliente.query.with_entities(Cliente.codigo).all()}
    bd_nombres = {_norm(c.nombre): c for c in Cliente.query.all()}

    # sociedades sin linea -> clientes adicionales
    extra = []
    for cod_g, b in data["bloque_grupos"].items():
        nom = _norm(b["nombre"])
        if nom not in nombres_cli and b["nombre"].upper() in SOCIEDADES_SIN_LINEA:
            extra.append({"nombre": b["nombre"], "codigo_nuevo": _siguiente_codigo(bd_codigos, data["codigos_base"], b["nombre"]),
                          "tipo": "PJ", "rf_excel": True, "valor_linea": 0.0})

    clientes_plan = []
    for c in data["clientes"]:
        nom = _norm(c["nombre"])
        ya = nom in bd_nombres
        # cobrado real: del prorrateo del grupo; sin grupo -> 0 (referencia = valor_linea)
        cob = round(cobrado.get(nom, 0.0), -2)
        presup = round(cob * (1 + ipc), -2)
        clientes_plan.append({
            "codigo": c["codigo"], "nombre": c["nombre"], "tipo": c["tipo"],
            "nit": c["nit"], "dv": c["dv"], "rf": bool(c["rf_excel"]),
            "cobrado_2024": cob, "presupuesto": presup, "ya_en_bd": ya,
            "obs": c["obs"][:200],
        })
    for c in extra:
        nom = _norm(c["nombre"])
        ya = nom in bd_nombres
        clientes_plan.append({
            "codigo": c["codigo_nuevo"], "nombre": c["nombre"], "tipo": c["tipo"],
            "nit": "", "dv": "", "rf": True,
            "cobrado_2024": 0.0, "presupuesto": 0.0, "ya_en_bd": ya,
            "obs": "Sociedad pagadora sin linea propia (codigo asignado por el sistema)",
        })

    # grupos: nombre = pagador (nombre del bloque), nota = codigo corto
    grupos_plan = []
    for g in data["grupos"]:
        b = data["bloque_grupos"].get(g["codigo"], {})
        grupos_plan.append({
            "codigo": g["codigo"], "nombre": b.get("nombre") or g["nombre"],
            "miembros": g["miembros"], "cobrado_real": b.get("cobrado_real", 0.0),
        })

    total_presup = sum(c["presupuesto"] for c in clientes_plan)
    return {"anio": anio, "ipc": ipc, "clientes": clientes_plan,
            "grupos": grupos_plan, "total_presupuesto": total_presup,
            "nuevos": sum(1 for c in clientes_plan if not c["ya_en_bd"]),
            "existentes": sum(1 for c in clientes_plan if c["ya_en_bd"])}


def aplicar(path):
    """Ejecuta la importacion (idempotente). Devuelve estadisticas."""
    plan = previsualizar(path)
    data = leer_excel(path)
    a = AnioCobro.query.filter_by(activo=True).first()
    if not a:
        raise RuntimeError("No hay año de cobro activo")
    cobrado = _cobrado_real_por_cliente(data)
    rf_excel = {_norm(c["nombre"]): bool(c["rf_excel"]) for c in data["clientes"]}

    stats = {"clientes_nuevos": 0, "clientes_actualizados": 0, "grupos": 0,
             "presupuestos": 0, "miembros": 0}

    # ---------- clientes ----------
    mapa = {}   # nombre_normalizado -> Cliente
    for cp in plan["clientes"]:
        nom = _norm(cp["nombre"])
        cli = db.session.query(Cliente).filter(Cliente.codigo == cp["codigo"]).first()
        if cli is None:
            cli = Cliente.query.filter(db.func.upper(Cliente.nombre) == nom).first()
        if cli is None:
            cli = Cliente(codigo=cp["codigo"], nombre=cp["nombre"].upper(),
                          tipo=cp["tipo"], nit=cp["nit"], dv=cp["dv"],
                          seccion="FACT", activo=True, rf_activa=cp["rf"],
                          cobrado_anterior=cp["cobrado_2024"],
                          cobrado_anterior_real=cp["cobrado_2024"])
            if cp["obs"]:
                cli.nota = cp["obs"][:280]
            db.session.add(cli)
            stats["clientes_nuevos"] += 1
        else:
            cli.seccion = "FACT"
            cli.tipo = cp["tipo"] or cli.tipo
            if cp["nit"]:
                cli.nit = cp["nit"]
                cli.dv = cp["dv"]
            cli.rf_activa = cp["rf"]
            cli.cobrado_anterior = cp["cobrado_2024"]
            cli.cobrado_anterior_real = cp["cobrado_2024"]
            stats["clientes_actualizados"] += 1
        mapa[nom] = cli
    db.session.flush()

    # ---------- presupuestos (anio activo) ----------
    for cp in plan["clientes"]:
        cli = mapa.get(_norm(cp["nombre"]))
        if not cli:
            continue
        p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
        if p is None:
            p = PresupuestoCliente(cliente_id=cli.id, anio_cobro=a.anio_cobro,
                                   valor=cp["presupuesto"],
                                   valor_pagado_ref=cp["cobrado_2024"],
                                   valor_final=cp["presupuesto"])
            db.session.add(p)
            stats["presupuestos"] += 1
        else:
            if not p.valor or p.valor == 0:      # no pisa presupuestos ya ajustados
                p.valor = cp["presupuesto"]
                p.valor_final = cp["presupuesto"]
                stats["presupuestos"] += 1
            p.valor_pagado_ref = cp["cobrado_2024"]

    # ---------- grupos de factura ----------
    lineas_valor = {_norm(c["nombre"]): c["valor_linea"] for c in data["clientes"]}
    grupos_bd = {(_norm(g.nombre) or ""): g for g in GrupoFamiliar.query.all()}
    for gp in plan["grupos"]:
        nom_g = _norm(gp["nombre"])
        g = grupos_bd.get(nom_g)
        if g is None:
            g = GrupoFamiliar(nombre=gp["nombre"].upper(), seccion="FACT")
            db.session.add(g)
            db.session.flush()
            grupos_bd[_norm(g.nombre)] = g
            stats["grupos"] += 1
        g.seccion = "FACT"
        if gp["codigo"]:
            g.nota = "Factura " + gp["codigo"] + " (Excel Grupos Facturación)"
        # pagador: el miembro cuyo nombre coincide con el nombre del grupo
        pagador = None
        for nm in gp["miembros"]:
            cli = mapa.get(_norm(nm))
            if not cli:
                continue
            if cli.grupo_id and cli.grupo_id != g.id:
                continue   # ya esta en otro grupo: no se reasigna
            cli.grupo_id = g.id
            stats["miembros"] += 1
            if _norm(nm) == nom_g:
                pagador = cli
        # sociedades sin linea: crear cliente si falta y hacerlo pagador
        if pagador is None and nom_g in [_norm(s) for s in SOCIEDADES_SIN_LINEA]:
            cp = next((c for c in plan["clientes"] if _norm(c["nombre"]) == nom_g), None)
            if cp:
                cli = mapa.get(nom_g)
                if cli is None:
                    cli = Cliente(codigo=cp["codigo"], nombre=cp["nombre"].upper(),
                                  tipo="PJ", seccion="FACT", activo=True,
                                  rf_activa=True, cobrado_anterior=0,
                                  cobrado_anterior_real=0,
                                  nota="Sociedad pagadora sin linea propia")
                    db.session.add(cli)
                    db.session.flush()
                    mapa[nom_g] = cli
                    p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
                    if p is None:
                        db.session.add(PresupuestoCliente(cliente_id=cli.id,
                                                          anio_cobro=a.anio_cobro,
                                                          valor=0, valor_pagado_ref=0,
                                                          valor_final=0))
                if not cli.grupo_id or cli.grupo_id == g.id:
                    cli.grupo_id = g.id
                    stats["miembros"] += 1
                pagador = cli
        for m in g.miembros:
            m.es_pagador = False
        if pagador:
            pagador.es_pagador = True
        elif g.miembros:
            first = g.miembros[0]
            first.es_pagador = True

    db.session.commit()
    return stats
