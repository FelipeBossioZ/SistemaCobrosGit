# -*- coding: utf-8 -*-
"""Lee del Excel del año anterior (hoja 'Cuentas de Cobro') lo EFECTIVAMENTE
cobrado por cliente. Para cuentas grupales prorratea el cobro entre los
miembros proporcionalmente al valor de cada línea."""
import os
import re
import shutil
import tempfile
from datetime import date, datetime, timedelta

import openpyxl

EXCEL_DEFECTO = (r"C:\OneDriveOficina\OneDrive\OFICINA\FELIPE\Oficina Felipe"
                 r"\6-Presupuestos\0-Presupuesto de cobros 2025 -FBZ.xlsx")


def _money_in(texto):
    """Extrae montos '$1.234.567' o '380.000' de un texto."""
    if not texto:
        return []
    montos = []
    for m in re.finditer(r"\$\s*([\d.,]+)", str(texto)):
        num = m.group(1).replace(".", "").replace(",", "")
        try:
            montos.append(float(num))
        except ValueError:
            pass
    return montos


def _as_fecha(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 60000:  # serial Excel
        return date(1899, 12, 30) + timedelta(days=int(v))
    return None


def leer_cobros_2025(path=None):
    """Devuelve {codigo: monto_efectivamente_cobrado}."""
    path = path or EXCEL_DEFECTO
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except PermissionError:  # abierto en Excel: lee una copia
        tmp = os.path.join(tempfile.gettempdir(), "cobros_anterior_leer.xlsx")
        shutil.copy2(path, tmp)
        wb = openpyxl.load_workbook(tmp, data_only=True, read_only=True)
    ws = wb["Cuentas de Cobro"]
    filas = []
    for r in ws.iter_rows(min_row=8, max_row=242, values_only=True):
        nombre = str(r[1] or "").strip()
        if not nombre:
            continue
        if nombre.upper().startswith("RETIRADOS"):
            break
        try:
            codigo = int(r[2])
        except (TypeError, ValueError):
            continue
        valor = float(r[5] or 0)
        cuenta_raw = str(r[6] or "").strip()
        estado = str(r[9] or "").strip().upper()
        fecha_pago = _as_fecha(r[11])
        obs = " ".join(str(x or "").strip() for x in r[12:14])
        montos = _money_in(obs)
        pagado = None
        if fecha_pago or estado.startswith("OK"):
            pagado = max(montos) if montos else valor
        filas.append({"codigo": codigo, "valor": valor,
                      "cuenta": cuenta_raw, "pagado": pagado})
    wb.close()

    # cuentas grupales: prorratear lo cobrado entre miembros por su valor
    resultado = {}
    por_cuenta = {}
    for f in filas:
        if f["cuenta"]:
            por_cuenta.setdefault(f["cuenta"], []).append(f)
        elif f["pagado"]:
            resultado[f["codigo"]] = f["pagado"]
    for fs in por_cuenta.values():
        cobrado = sum(f["pagado"] or 0 for f in fs)
        if cobrado <= 0:
            continue
        total = sum(f["valor"] for f in fs)
        if len(fs) == 1 or total <= 0:
            for f in fs:
                if f["pagado"]:
                    resultado[f["codigo"]] = resultado.get(f["codigo"], 0) + (f["pagado"] if len(fs) == 1 else cobrado)
            if len(fs) == 1 and not fs[0]["pagado"]:
                resultado[fs[0]["codigo"]] = cobrado
            continue
        for f in fs:
            parte = cobrado * (f["valor"] / total)
            if parte:
                resultado[f["codigo"]] = resultado.get(f["codigo"], 0) + parte
    return resultado
