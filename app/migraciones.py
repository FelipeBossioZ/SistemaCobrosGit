# -*- coding: utf-8 -*-
"""Migraciones ligeras: agrega columnas nuevas sin tocar datos existentes."""
from sqlalchemy import text


def ejecutar(db):
    """Idempotente: solo agrega lo que falte."""
    with db.engine.connect() as con:
        cols = {r[1] for r in con.execute(text("PRAGMA table_info(clientes)"))}
        if "cobrado_anterior_real" not in cols:
            con.execute(text("ALTER TABLE clientes ADD COLUMN cobrado_anterior_real NUMERIC DEFAULT 0"))
            con.commit()
        if "moroso_nota" not in cols:
            con.execute(text("ALTER TABLE clientes ADD COLUMN moroso_nota VARCHAR(300) DEFAULT ''"))
            con.commit()
        if "moroso_cerrado" not in cols:
            con.execute(text("ALTER TABLE clientes ADD COLUMN moroso_cerrado BOOLEAN DEFAULT 0"))
            con.commit()
