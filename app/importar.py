# -*- coding: utf-8 -*-
"""Importación inicial desde el Excel 'Presupuesto de cobros'."""
import re
from datetime import datetime, date

import openpyxl
from .models import (db, Parametro, AnioCobro, Cliente, PresupuestoCliente,
                     CuentaCobro, CuentaLinea, Envio, Ajuste, Pago)

SKIP_PREFIXES = ("TOTAL", "PERSONAS", "RETIRADOS", "ACUMULADO", "PRESUPUESTO",
                 "CUENTAS", "AÑO", "NO ELABORADAS", "Diferencia")


def _val(row, idx):
    v = row[idx] if idx < len(row) else None
    return v


def _txt(v):
    if v is None:
        return ""
    return str(v).strip()


def _norm_forma(v):
    s = _txt(v)
    s = s.replace("Tranferencia", "Transferencia").replace("TRANSFERENCIA", "Transferencia")
    if s.lower() in ("wpp", "whatsapp"):
        return "WhatsApp"
    return s


def _money_in(texto):
    """Extrae montos '$1.234.567' o '380.000' de un texto."""
    if not texto:
        return []
    t = str(texto)
    montos = []
    for m in re.finditer(r"\$\s*([\d.,]+)", t):
        num = m.group(1).replace(".", "").replace(",", "")
        try:
            montos.append(float(num))
        except ValueError:
            pass
    return montos


def _as_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def _parse_cuenta_num(v):
    """'26-002' -> ('26', 2). None si no corresponde."""
    s = _txt(v)
    m = re.match(r"^(\d{2})-(\d+)$", s)
    if not m:
        return None
    return m.group(1), int(m.group(2))


def leer_filas_clientes(path):
    """Lee la hoja 'Cuentas de Cobro' y devuelve lista de dicts de clientes activos."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Cuentas de Cobro"]
    filas = []
    tipo_actual = "PN"
    for r in ws.iter_rows(min_row=8, max_row=242, values_only=True):
        nombre = _txt(_val(r, 1))
        if not nombre:
            continue
        upper = nombre.upper()
        if upper.startswith("PERSONAS JUR"):
            tipo_actual = "PJ"
            continue
        if upper.startswith("PERSONAS") or upper.startswith("RETIRADOS"):
            if "RETIRADOS" in upper:
                break  # fin de activos
            continue
        if any(upper.startswith(p) for p in SKIP_PREFIXES):
            continue
        codigo = _val(r, 2)
        if codigo in (None, ""):
            continue
        try:
            codigo = int(codigo)
        except (TypeError, ValueError):
            continue
        filas.append({
            "codigo": codigo,
            "nombre": re.sub(r"\s+", " ", nombre).strip(),
            "tipo": "PJ" if tipo_actual == "PJ" else "PN",
            "nit": _txt(_val(r, 3)),
            "dv": _txt(_val(r, 4)),
            "valor": float(_val(r, 5) or 0),
            "cuenta_raw": _txt(_val(r, 6)),
            "medio_envio": _txt(_val(r, 7)),
            "fecha_envio": _as_date(_val(r, 8)),
            "estado_txt": _txt(_val(r, 9)).upper(),
            "forma_pago": _norm_forma(_val(r, 10)),
            "fecha_pago": _as_date(_val(r, 11)),
            "obs1": _txt(_val(r, 12)),
            "obs2": _txt(_val(r, 13)),
        })
    return filas


def leer_parametros(path):
    """Lee IPC, mínimas y consecutivo de la hoja 'Cuentas de Cobro'."""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Cuentas de Cobro"]
    rows = list(ws.iter_rows(min_row=1, max_row=6, values_only=True))
    ipc = float(rows[4][16] or 0)          # Q5 (valor al lado del rótulo IPC en P5)
    minima = float(rows[2][12] or 0)       # M3
    minima1 = float(rows[2][13] or 0)      # N3
    return {"ipc": ipc, "minima": minima, "minima_primera": minima1}


def importar(path, anio_cobro=2026, anio_gravable=2025, prefijo="26"):
    """Importa clientes activos, presupuestos y las cuentas del ciclo actual."""
    filas = leer_filas_clientes(path)
    pars = leer_parametros(path)

    anio = AnioCobro.query.filter_by(anio_cobro=anio_cobro).first()
    if anio is None:
        anio = AnioCobro(
            anio_cobro=anio_cobro, anio_gravable=anio_gravable, prefijo=prefijo,
            consecutivo_inicial=1, ipc=pars["ipc"], valor_minima=pars["minima"],
            valor_minima_primera=pars["minima_primera"], activo=True,
            concepto=f"Asesoría tributaria año gravable {anio_gravable}",
        )
        db.session.add(anio)
    else:
        anio.ipc = pars["ipc"]
        anio.valor_minima = pars["minima"]
        anio.valor_minima_primera = pars["minima_primera"]

    db.session.flush()

    stats = {"clientes": 0, "presupuestos": 0, "cuentas": 0}

    # 1) Clientes + presupuestos
    clientes_por_codigo = {}
    for f in filas:
        cli = Cliente.query.filter_by(codigo=f["codigo"]).first()
        if cli is None:
            cli = Cliente(codigo=f["codigo"], nombre=f["nombre"], tipo=f["tipo"],
                          nit=f["nit"], dv=f["dv"], activo=True)
            db.session.add(cli)
            stats["clientes"] += 1
        else:
            cli.nombre = f["nombre"]
            cli.activo = True
        db.session.flush()
        clientes_por_codigo[f["codigo"]] = cli

        # nota con referencia de cuenta del año anterior (prefijo distinto)
        parsed = _parse_cuenta_num(f["cuenta_raw"])
        if parsed and parsed[0] != prefijo:
            cli.nota = f"C de C año anterior: {f['cuenta_raw']}"

        p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=anio_cobro).first()
        if p is None:
            p = PresupuestoCliente(cliente_id=cli.id, anio_cobro=anio_cobro, valor=f["valor"])
            db.session.add(p)
        else:
            p.valor = f["valor"]
        stats["presupuestos"] += 1

    db.session.flush()

    # 2) Cuentas existentes del ciclo actual (agrupadas por número)
    por_numero = {}
    for f in filas:
        parsed = _parse_cuenta_num(f["cuenta_raw"])
        if parsed and parsed[0] == prefijo:
            por_numero.setdefault(parsed[1], []).append(f)

    for numero, fs in sorted(por_numero.items()):
        cuenta = CuentaCobro.query.filter_by(anio_cobro_id=anio.id, numero=numero).first()
        if cuenta is None:
            cuenta = CuentaCobro(anio_cobro_id=anio.id, numero=numero)
            db.session.add(cuenta)
            stats["cuentas"] += 1
        # fecha: la mínima de fechas de envío
        fechas = [f["fecha_envio"] for f in fs if f["fecha_envio"]]
        cuenta.fecha = min(fechas) if fechas else date(anio_cobro, 1, 1)
        db.session.flush()
        cuenta.lineas.clear()

        for f in fs:
            cli = clientes_por_codigo.get(f["codigo"])
            if cli is None:
                continue
            db.session.add(CuentaLinea(cuenta=cuenta, cliente_id=cli.id, valor=f["valor"]))
        db.session.flush()

        total = cuenta.total

        # envío
        if cuenta.envios.count() == 0:
            for f in fs:
                if f["medio_envio"] or f["fecha_envio"]:
                    db.session.add(Envio(cuenta=cuenta, medio=_norm_forma(f["medio_envio"]) or "Correo",
                                         fecha=f["fecha_envio"] or cuenta.fecha,
                                         nota="Importado del Excel"))
                    break

        # pago + ajuste por autodescuento
        if cuenta.pagos.count() == 0:
            obs = " | ".join([f["obs1"] for f in fs if f["obs1"]] +
                             [f["obs2"] for f in fs if f["obs2"]])
            pagadas = [f for f in fs if f["estado_txt"] == "PAGADO"]
            if pagadas:
                f = pagadas[0]
                montos = _money_in(obs)
                pago_val = total
                ajuste_val = 0.0
                if montos and abs(max(montos) - total) > 1:
                    pago_val = max(montos)
                    ajuste_val = total - pago_val
                if ajuste_val > 0:
                    db.session.add(Ajuste(cuenta=cuenta, fecha=f["fecha_pago"] or cuenta.fecha,
                                          valor=ajuste_val,
                                          motivo=obs or "Autodescuento (importado)"))
                db.session.add(Pago(cuenta=cuenta, fecha=f["fecha_pago"] or cuenta.fecha,
                                    valor=pago_val, forma=f["forma_pago"] or "Transferencia",
                                    nota=obs))

        db.session.flush()
        cuenta.marcar_estado()

    # consecutivo siguiente
    max_num = db.session.query(db.func.max(CuentaCobro.numero)).filter_by(anio_cobro_id=anio.id).scalar()
    anio.numero_siguiente = (max_num or 0) + 1

    # 3) Parámetros del emisor (solo si están vacíos)
    if not Parametro.get("emisor_nombre"):
        Parametro.set("emisor_nombre", "DIEGO ALBERTO FERNÁNDEZ FERNÁNDEZ")
        Parametro.set("emisor_cc", "71.662.891")
        Parametro.set("emisor_direccion", "CR 46 49 A 27 OF 605")
        Parametro.set("emisor_telefonos", "511 1353")
        Parametro.set("emisor_ciudad", "MEDELLÍN")
        Parametro.set("banco_info",
                      "Bancolombia Ahorros\n"
                      "Cuenta No.: 006 985 327 51\n"
                      "A nombre de: Diego Alberto Fernández Fernández\n"
                      "C. c. No.: 71.662.891\n"
                      "Llave: @diego2891")
        Parametro.set("formas_pago", "Transferencia|Consignación|Llave Bancolombia|Otro banco|Efectivo")

    db.session.commit()
    return stats
