# -*- coding: utf-8 -*-
"""Migraciones ligeras: agrega columnas nuevas sin tocar datos existentes."""
from sqlalchemy import text


def ejecutar(db):
    """Idempotente: solo agrega lo que falte."""
    with db.engine.connect() as con:
        cols_pr = {r[1] for r in con.execute(text("PRAGMA table_info(presupuestos)"))}
        if cols_pr and "valor_final" not in cols_pr:
            con.execute(text("ALTER TABLE presupuestos ADD COLUMN valor_final FLOAT"))
            con.commit()
        # Facturacion (fase 1): seccion en grupos/clientes/cuentas + folio + pct IVA/RF
        cols_gr = {r[1] for r in con.execute(text("PRAGMA table_info(grupos_familiares)"))}
        if cols_gr and "seccion" not in cols_gr:
            con.execute(text("ALTER TABLE grupos_familiares ADD COLUMN seccion VARCHAR(4) DEFAULT 'CDEC'"))
            con.commit()
        cols_ct = {r[1] for r in con.execute(text("PRAGMA table_info(cuentas_cobro)"))}
        if cols_ct and "seccion" not in cols_ct:
            con.execute(text("ALTER TABLE cuentas_cobro ADD COLUMN seccion VARCHAR(4) DEFAULT 'CDEC'"))
            con.commit()
        if cols_ct and "folio_factura" not in cols_ct:
            con.execute(text("ALTER TABLE cuentas_cobro ADD COLUMN folio_factura VARCHAR(60) DEFAULT ''"))
            con.commit()
        if cols_ct and "pct_iva" not in cols_ct:
            con.execute(text("ALTER TABLE cuentas_cobro ADD COLUMN pct_iva FLOAT"))
            con.commit()
        if cols_ct and "pct_rf" not in cols_ct:
            con.execute(text("ALTER TABLE cuentas_cobro ADD COLUMN pct_rf FLOAT"))
            con.commit()
        cols = {r[1] for r in con.execute(text("PRAGMA table_info(clientes)"))}
        if cols and "seccion" not in cols:
            con.execute(text("ALTER TABLE clientes ADD COLUMN seccion VARCHAR(4) DEFAULT 'CDEC'"))
            con.commit()
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
        if "renta_base" not in cols:
            con.execute(text("ALTER TABLE clientes ADD COLUMN renta_base FLOAT"))
        con.commit()
        # Tarifario: estratos de renta por patrimonio neto (guia editable)
        con.execute(text("""CREATE TABLE IF NOT EXISTS estratos_tarifa (
            id INTEGER PRIMARY KEY,
            orden INTEGER NOT NULL,
            nombre VARCHAR(60) NOT NULL,
            pat_min FLOAT,
            pat_max FLOAT,
            valor FLOAT,
            factor FLOAT,
            activo BOOLEAN DEFAULT 1
        )"""))
        _n = con.execute(text("SELECT COUNT(*) FROM estratos_tarifa")).scalar() or 0
        if not _n:
            con.execute(text("""INSERT INTO estratos_tarifa
                (orden, nombre, pat_min, pat_max, valor, factor, activo) VALUES
                (1, 'Minima Especial (0-100M)', 0, 100000000, NULL, NULL, 1),
                (2, 'Basica (100-300M)', 100000000, 300000000, 350000, 1.0, 1),
                (3, '300M - 500M', 300000000, 500000000, 395000, 1.13, 1),
                (4, '500M - 1.000M', 500000000, 1000000000, 670000, 1.92, 1),
                (5, '1.000M - 2.000M', 1000000000, 2000000000, 1005000, 2.88, 1),
                (6, '2.000M - 3.000M', 2000000000, 3000000000, 1355000, 3.88, 1),
                (7, 'Mas de 3.000M', 3000000000, NULL, 1960000, 5.6, 1)"""))
        con.commit()
