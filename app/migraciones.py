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
        # Fase B: catálogo de asesorías (create_all también las crea; esto cubre
        # BDs heredadas si create_all no alcanzara a correr)
        con.execute(text("""CREATE TABLE IF NOT EXISTS asesorias_catalogo (
            id INTEGER PRIMARY KEY,
            orden INTEGER,
            codigo VARCHAR(40) NOT NULL,
            nombre VARCHAR(120) NOT NULL,
            tipo VARCHAR(8),
            defecto_pct FLOAT,
            defecto_valor FLOAT,
            base_min VARCHAR(60),
            activo BOOLEAN
        )"""))
        con.execute(text("""CREATE TABLE IF NOT EXISTS asesorias_cliente (
            id INTEGER PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            asesoria_id INTEGER NOT NULL,
            incluir BOOLEAN,
            pct FLOAT,
            valor FLOAT,
            CONSTRAINT uq_asesoria_cliente UNIQUE (cliente_id, asesoria_id),
            FOREIGN KEY(cliente_id) REFERENCES clientes (id),
            FOREIGN KEY(asesoria_id) REFERENCES asesorias_catalogo (id)
        )"""))
        con.commit()
        con.execute(text("""CREATE TABLE IF NOT EXISTS presupuesto_historial (
            id INTEGER PRIMARY KEY,
            cliente_id INTEGER NOT NULL,
            anio_cobro INTEGER NOT NULL,
            valor_anterior FLOAT,
            valor_nuevo FLOAT,
            motivo VARCHAR(300) NOT NULL,
            fecha DATE,
            FOREIGN KEY(cliente_id) REFERENCES clientes (id)
        )"""))
        con.commit()
        # Motor de asesorias (parte 1): columnas nuevas
        cols_cat = {r[1] for r in con.execute(text("PRAGMA table_info(asesorias_catalogo)"))}
        if cols_cat and "es_fija" not in cols_cat:
            con.execute(text("ALTER TABLE asesorias_catalogo ADD COLUMN es_fija BOOLEAN DEFAULT 0"))
        cols_ac = {r[1] for r in con.execute(text("PRAGMA table_info(asesorias_cliente)"))}
        if cols_ac and "cantidad" not in cols_ac:
            con.execute(text("ALTER TABLE asesorias_cliente ADD COLUMN cantidad INTEGER DEFAULT 1"))
        if cols_ac and "nota" not in cols_ac:
            con.execute(text("ALTER TABLE asesorias_cliente ADD COLUMN nota VARCHAR(120) DEFAULT ''"))
        if "renta_base" not in cols:
            con.execute(text("ALTER TABLE clientes ADD COLUMN renta_base FLOAT"))
        con.commit()
