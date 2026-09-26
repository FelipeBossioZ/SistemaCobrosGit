# -*- coding: utf-8 -*-
"""Respaldo automatico de la BD al arrancar + chequeo de integridad.
- Un respaldo por dia: Respaldos BD/cobros_YYYY-MM-DD.db (junto al proyecto)
- Retencion: 30 dias
- Nunca bloquea el arranque: cualquier error se ignora."""
import os
import re
import shutil
import sqlite3
from datetime import date, timedelta

DIAS_RETENCION = 30


def respaldo_arranque(app):
    try:
        src = os.path.join(app.instance_path, "cobros.db")
        if not os.path.isfile(src):
            return
        proyecto = os.path.dirname(app.instance_path)
        destino_dir = os.path.join(proyecto, "Respaldos BD")
        os.makedirs(destino_dir, exist_ok=True)
        destino = os.path.join(destino_dir, "cobros_%s.db" % date.today().strftime("%Y-%m-%d"))
        if not os.path.isfile(destino):
            shutil.copy2(src, destino)
        con = sqlite3.connect(src)
        try:
            integridad = con.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            con.close()
        _limpiar_viejos(destino_dir)
        try:
            app.logger.info("Respaldos BD: ok (integridad %s)", integridad)
        except Exception:
            pass
    except Exception:
        try:
            app.logger.warning("Respaldos BD: no se pudo respaldar al arrancar")
        except Exception:
            pass


def _limpiar_viejos(destino_dir):
    limite = date.today() - timedelta(days=DIAS_RETENCION)
    patron = re.compile(r"^cobros_\d{4}-\d{2}-\d{2}\.db$")
    for nombre in os.listdir(destino_dir):
        if not patron.match(nombre):
            continue
        try:
            fecha = date.fromisoformat(nombre[7:17])
        except ValueError:
            continue
        if fecha < limite:
            try:
                os.remove(os.path.join(destino_dir, nombre))
            except OSError:
                pass
