# -*- coding: utf-8 -*-
"""Modelos de datos del Sistema de Cobros."""
from datetime import date, datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Estados de una Cuenta de Cobro
ESTADOS = ("BORRADOR", "ENVIADA", "PAGADA", "ANULADA")


class Parametro(db.Model):
    """Parámetros generales del emisor (editables, llave/valor)."""
    __tablename__ = "parametros"
    clave = db.Column(db.String(60), primary_key=True)
    valor = db.Column(db.String(500))

    @staticmethod
    def get(clave, defecto=""):
        p = db.session.get(Parametro, clave)
        return p.valor if p and p.valor is not None else defecto

    @staticmethod
    def set(clave, valor):
        p = db.session.get(Parametro, clave)
        if p is None:
            p = Parametro(clave=clave, valor=valor)
            db.session.add(p)
        else:
            p.valor = valor


class AnioCobro(db.Model):
    """Configuración por año de cobro (ciclo: gravable -> cobro)."""
    __tablename__ = "anios_cobro"

    id = db.Column(db.Integer, primary_key=True)
    anio_cobro = db.Column(db.Integer, unique=True, nullable=False)   # 2026
    anio_gravable = db.Column(db.Integer, nullable=False)             # 2025
    prefijo = db.Column(db.String(10), nullable=False)                # "26"
    consecutivo_inicial = db.Column(db.Integer, default=1)
    ipc = db.Column(db.Float, default=0.0)                            # ej 0.051
    valor_minima = db.Column(db.Float, default=0.0)                   # Mínima Mvto
    valor_minima_primera = db.Column(db.Float, default=0.0)           # Mínima 1ª vez
    activo = db.Column(db.Boolean, default=True)

    concepto = db.Column(db.String(200), default="")                  # texto del PDF
    emisor_nombre = db.Column(db.String(150), default="")
    emisor_cc = db.Column(db.String(40), default="")
    emisor_direccion = db.Column(db.String(200), default="")
    emisor_telefonos = db.Column(db.String(100), default="")
    emisor_ciudad = db.Column(db.String(80), default="")
    banco_info = db.Column(db.Text, default="")                       # líneas cuenta bancaria
    numero_siguiente = db.Column(db.Integer, default=1)               # consecutivo real

    cuentas = db.relationship("CuentaCobro", backref="anio", lazy="dynamic")

    @property
    def concepto_texto(self):
        if self.concepto:
            return self.concepto
        return f"Asesoría tributaria año gravable {self.anio_gravable}"


class GrupoFamiliar(db.Model):
    """Grupo familiar. Un cliente pertenece a 0..1 grupo. Uno de ellos es el pagador."""
    __tablename__ = "grupos_familiares"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    nota = db.Column(db.String(300), default="")

    miembros = db.relationship("Cliente", backref="grupo", lazy="dynamic")

    @property
    def pagador(self):
        for m in self.miembros:
            if m.es_pagador:
                return m
        return self.miembros.first()


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.Integer, unique=True, nullable=False)  # código histórico del Excel
    nombre = db.Column(db.String(150), nullable=False, index=True)
    tipo = db.Column(db.String(2), default="PN")                 # PN | PJ
    nit = db.Column(db.String(20), default="")                   # CC o NIT
    dv = db.Column(db.String(2), default="")
    ciudad = db.Column(db.String(80), default="MEDELLÍN")
    direccion = db.Column(db.String(200), default="")
    telefonos = db.Column(db.String(100), default="")
    email = db.Column(db.String(150), default="")
    activo = db.Column(db.Boolean, default=True)
    nota = db.Column(db.String(300), default="")                 # ej: "NO DECLARANTE", referencia año anterior
    cobrado_anterior = db.Column(db.Numeric(14, 2), default=0)   # C de C del año anterior (referencia histórica)
    cobrado_anterior_real = db.Column(db.Numeric(14, 2), default=0)  # EFECTIVAMENTE cobrado año anterior (Excel)
    moroso_nota = db.Column(db.String(300), default="")             # nota del módulo de morosos
    moroso_cerrado = db.Column(db.Boolean, default=False)           # True = pagó de menos por acuerdo interno (no es moroso)
    decl_renta = db.Column(db.String(12), default="")            # ""=sin dato, NO_OBLIGADO, PRESENTADA
    renta_base = db.Column(db.Float)                             # base confirmada del paquete (None = derivar del presupuesto)

    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_familiares.id"))
    es_pagador = db.Column(db.Boolean, default=False)            # a nombre de quién sale la cuenta del grupo
    trato = db.Column(db.String(10), default="")                 # "" = automático, "SR", "SRA"
    presupuesto = db.relationship("PresupuestoCliente", backref="cliente", lazy="dynamic",
                                  cascade="all, delete-orphan")

    @property
    def nit_formateado(self):
        """NIT con separador de miles, estilo 22,126,399."""
        n = (self.nit or "").strip()
        if not n:
            return ""
        try:
            return f"{int(n):,}"
        except ValueError:
            return n

    # ---------------- scanner de declaraciones ----------------
    DECL_ETIQUETAS = {"": "Sin dato", "NO_OBLIGADO": "No obligado", "PRESENTADA": "Renta presentada"}

    @property
    def decl_ok(self):
        """True si este cliente solo está OK por sí mismo (presentada o no obligado)."""
        return self.decl_renta in ("PRESENTADA", "NO_OBLIGADO")

    @property
    def grupo_al_dia(self):
        """Si tiene grupo: True cuando TODOS los miembros están presentada/no obligado."""
        if not self.grupo_id:
            return None
        return all(m.decl_ok for m in self.grupo.miembros)

    @property
    def puede_cobrarse(self):
        """Cobrable = él al día y (si es de grupo) todo el grupo al día."""
        if not self.decl_ok:
            return False
        g = self.grupo_al_dia
        return True if g is None else bool(g)

    @property
    def estado_cobro_grupo(self):
        """Texto corto para badges: OK / GRUPO OK / PENDIENTE X."""
        if not self.decl_ok:
            return "FALTA RENTA"
        if self.grupo_id:
            faltan = [m.nombre for m in self.grupo.miembros if not m.decl_ok]
            if faltan:
                return "GRUPO PENDIENTE: " + ", ".join(faltan[:3]) + ("..." if len(faltan) > 3 else "")
            return "GRUPO AL DÍA"
        return "AL DÍA"


class PresupuestoHistorial(db.Model):
    """Auditoría de cambios del presupuesto anual de un cliente.
    El motivo es obligatorio: queda documentado por qué se movió el valor."""
    __tablename__ = "presupuesto_historial"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True)
    anio_cobro = db.Column(db.Integer, nullable=False)
    valor_anterior = db.Column(db.Float, default=0.0)
    valor_nuevo = db.Column(db.Float, default=0.0)
    motivo = db.Column(db.String(300), nullable=False)
    fecha = db.Column(db.Date, nullable=False)


class AsesoriaCatalogo(db.Model):
    """Catálogo de asesorías/trámites que la oficina cobra.
    Los estándares de la oficina viven aquí (editables en Parámetros → Asesorías).
    tipo: PN | PJ | TODOS.  pct: % del valor base;  valor: tarifa fija.
    base_min: texto informativo ('RETEFUENTE', 'SMLV/mes', 'IVA base $...', ...)."""
    __tablename__ = "asesorias_catalogo"

    id = db.Column(db.Integer, primary_key=True)
    orden = db.Column(db.Integer, default=100)
    codigo = db.Column(db.String(40), unique=True, nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(8), default="TODOS")      # PN | PJ | TODOS
    defecto_pct = db.Column(db.Float, default=0.0)        # % estándar de la oficina
    defecto_valor = db.Column(db.Float, default=0.0)      # tarifa fija estándar
    base_min = db.Column(db.String(60), default="")
    es_fija = db.Column(db.Boolean, default=False)   # True = tarifa fija x cantidad; False = % de la renta base
    activo = db.Column(db.Boolean, default=True)


class AsesoriaCliente(db.Model):
    """Asesorías incluidas en el paquete de un cliente para el año de cobro.
    pct/valor en None => usa el estándar del catálogo. La suma es el total del
    paquete que se compara con el presupuesto anual del cliente."""
    __tablename__ = "asesorias_cliente"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    asesoria_id = db.Column(db.Integer, db.ForeignKey("asesorias_catalogo.id"), nullable=False)
    incluir = db.Column(db.Boolean, default=True)
    pct = db.Column(db.Float)                             # None = estándar
    valor = db.Column(db.Float)                           # None = estándar
    cantidad = db.Column(db.Integer, default=1)           # solo tarifas fijas (IVA, RF...)
    nota = db.Column(db.String(120), default="")          # OTRAS: que se esta cobrando (solo interno, no sale en PDF)

    __table_args__ = (db.UniqueConstraint("cliente_id", "asesoria_id", name="uq_asesoria_cliente"),)


def saludo_de_cliente(p):
    """'Señora' / 'Señor' / 'Señores' según trato guardado, tipo o deducción del nombre.

    Formato de la oficina: APELLIDO [APELLIDO] NOMBRES (con partículas DE LA / DEL...).
    Solo se deduce por el nombre de pila (lo que va después de los apellidos);
    si es ambiguo (RAFAEL, iniciales, un solo apellido) queda neutro 'Señores'
    y se fija a mano con el campo trato."""
    if p is None:
        return "Señores"
    t = (getattr(p, "trato", "") or "").strip().upper()
    if t == "SRA":
        return "Señora"
    if t == "SR":
        return "Señor"
    if (getattr(p, "tipo", "") or "") == "PJ":
        return "Señores"

    import unicodedata

    def _limpia(w):
        s = "".join(ch for ch in unicodedata.normalize("NFD", w.strip(".,;"))
                    if unicodedata.category(ch) != "Mn")
        return s.upper()

    PARTICULAS = {"DE", "LA", "DEL", "LOS", "LAS", "SAN", "SANTA", "VON", "VAN", "DA", "DU"}
    SUFIJOS = {"S.A.", "S.A.S", "S.A.S.", "S.E.", "LTDA", "S.C.A.", "S.C.S.", "CIA"}
    FEMENINOS_O = {"CONSUELO", "ROSARIO", "ROCIO", "AMPARO", "SOCORRO", "MILAGROS", "DOLORES"}

    palabras = [_limpia(w) for w in (p.nombre or "").split()]
    palabras = [w for w in palabras if w]
    if not palabras:
        return "Señores"
    # nombres femeninos clásicos terminados en O, en cualquier posición
    if any(w in FEMENINOS_O for w in palabras):
        return "Señora"
    # quitar partículas de los apellidos y quedarnos con lo que puede ser nombre de pila
    palos = [w for w in palabras if w not in PARTICULAS]
    pila = palos[2:]  # tras los dos apellidos
    if not pila:
        return "Señores"
    ultima = pila[-1]
    # sufijo societario o inicial suelta ("J.", "F") -> neutro
    if ultima in SUFIJOS or len(ultima) <= 2:
        return "Señores"
    if ultima.endswith("A"):
        return "Señora"
    if ultima.endswith("O"):
        return "Señor"
    # ambiguo (RAFAEL, CARLOS ANDRES ya cubierto, etc.) -> neutro
    return "Señores"


class PresupuestoCliente(db.Model):
    """Valor presupuestado de cobro por cliente y año de cobro.
    Es el 'VALOR A ELABORAR LA CUENTA DE COBRO' del Excel."""
    __tablename__ = "presupuestos"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    anio_cobro = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Float, default=0.0)
    valor_pagado_ref = db.Column(db.Float, default=0.0)  # pago real año anterior (referencia negociación)

    __table_args__ = (db.UniqueConstraint("cliente_id", "anio_cobro", name="uq_presupuesto"),)


class CuentaCobro(db.Model):
    """Documento Cuenta de Cobro. Tiene 1..n líneas (clientes)."""
    __tablename__ = "cuentas_cobro"

    id = db.Column(db.Integer, primary_key=True)
    anio_cobro_id = db.Column(db.Integer, db.ForeignKey("anios_cobro.id"), nullable=False)
    numero = db.Column(db.Integer, nullable=False)                 # consecutivo entero
    fecha = db.Column(db.Date, default=date.today)
    estado = db.Column(db.String(10), default="BORRADOR")          # BORRADOR|ENVIADA|PAGADA|ANULADA
    nota = db.Column(db.String(500), default="")                  # NOTA INTERNA: nunca sale en el PDF
    observaciones = db.Column(db.String(500), default="")         # observaciones visibles en el PDF (sección OBS.)
    pagador_cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"))  # override de pagador para esta cuenta
    motivo_anulacion = db.Column(db.String(300), default="")   # obligatorio al anular

    lineas = db.relationship("CuentaLinea", backref="cuenta", lazy="joined",
                             cascade="all, delete-orphan", order_by="CuentaLinea.id")
    envios = db.relationship("Envio", backref="cuenta", lazy="dynamic",
                             cascade="all, delete-orphan")
    pagos = db.relationship("Pago", backref="cuenta", lazy="dynamic",
                            cascade="all, delete-orphan")
    ajustes = db.relationship("Ajuste", backref="cuenta", lazy="dynamic",
                              cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("anio_cobro_id", "numero", name="uq_numero_cuenta"),)

    @property
    def numero_formateado(self):
        a = self.anio
        return f"{a.prefijo}-{self.numero:03d}" if a else str(self.numero)

    @property
    def total(self):
        return sum(l.valor for l in self.lineas if l.estado != "ANULADA")

    @property
    def total_pagado(self):
        return sum(p.valor for p in self.pagos)

    @property
    def total_ajustes(self):
        return sum(a.valor for a in self.ajustes)

    @property
    def saldo(self):
        return self.total - self.total_ajustes - self.total_pagado

    @property
    def ultimo_envio(self):
        return self.envios.order_by(Envio.fecha.desc(), Envio.id.desc()).first()

    @property
    def pagador_principal(self):
        """Cliente 'cabeza' de la cuenta: override de la cuenta, pagador del grupo o primera línea."""
        if self.pagador_cliente_id:
            cli = db.session.get(Cliente, self.pagador_cliente_id)
            if cli:
                return cli
        for l in self.lineas:
            c = l.cliente
            if c and c.es_pagador:
                return c
        return self.lineas[0].cliente if self.lineas else None

    def marcar_estado(self):
        """Recalcula estado automático salvo ANULADA (el número queda conservado)."""
        if self.estado == "ANULADA":
            return
        if self.saldo <= 0 and self.total > 0:
            self.estado = "PAGADA"
        elif self.envios.count() > 0:
            self.estado = "ENVIADA"
        else:
            self.estado = "BORRADOR"


class CuentaLinea(db.Model):
    """Una línea de la Cuenta de Cobro: un cliente y su valor."""
    __tablename__ = "cuentas_lineas"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_cobro.id"), nullable=False)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    valor = db.Column(db.Float, default=0.0)
    concepto = db.Column(db.String(200), default="")                # opcional: concepto propio de la línea
    estado = db.Column(db.String(10), default="ACTIVA")            # ACTIVA | ANULADA

    cliente = db.relationship("Cliente")


class Envio(db.Model):
    """Registro de envíos de la cuenta (permite reenvíos)."""
    __tablename__ = "envios"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_cobro.id"), nullable=False)
    fecha = db.Column(db.Date, default=date.today)
    medio = db.Column(db.String(30), nullable=False)   # Correo | WhatsApp | Correo y WhatsApp | Físico | Otro
    nota = db.Column(db.String(300), default="")


class Ajuste(db.Model):
    """Descuento o cargo aplicado por el cliente (ej. autodescuento)."""
    __tablename__ = "ajustes"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_cobro.id"), nullable=False)
    fecha = db.Column(db.Date, default=date.today)
    valor = db.Column(db.Float, default=0.0)   # positivo descuenta, negativo suma
    motivo = db.Column(db.String(300), default="")


class TrabajoAdicional(db.Model):
    """Trabajo adicional hecho a un cliente fuera del presupuesto anual
    (ej. consulta, requerimiento DIAN, trámite extra). Para revisar antes de
    cobrar el próximo año y no olvidar cobrarlo."""
    __tablename__ = "trabajos_adicionales"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False)
    fecha = db.Column(db.Date, default=date.today)
    descripcion = db.Column(db.String(300), nullable=False)
    valor = db.Column(db.Float, default=0.0)          # 0 = por definir
    anio_cobro = db.Column(db.Integer, default=0)     # año de cobro al que pertenece
    estado = db.Column(db.String(12), default="PENDIENTE")   # PENDIENTE | COBRADO
    marcado = db.Column(db.Boolean, default=False)    # ya incluido en una cuenta
    creado = db.Column(db.DateTime, default=datetime.utcnow)

    cliente = db.relationship("Cliente", backref=db.backref(
        "trabajos", lazy="dynamic", cascade="all, delete-orphan"))


class Pago(db.Model):
    """Pago (o abono parcial) de una cuenta."""
    __tablename__ = "pagos"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_cobro.id"), nullable=False)
    fecha = db.Column(db.Date, default=date.today)
    valor = db.Column(db.Float, default=0.0)
    forma = db.Column(db.String(60), default="Transferencia")  # cómo pagó el cliente (trazabilidad)
    nota = db.Column(db.String(300), default="")

    @staticmethod
    def formas_pago():
        raw = Parametro.get("formas_pago", "Transferencia|Consignación|Llave Bancolombia|Otro banco|Efectivo")
        return [x.strip() for x in raw.split("|") if x.strip()]


class Tarea(db.Model):
    """Nota rapida / pendiente por cliente (ej. 'llamar', 'falta X').
    Queda en historial: hecha=False pendiente, hecha=True cumplida."""
    __tablename__ = "tareas"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=False, index=True)
    texto = db.Column(db.String(500), nullable=False)
    fecha = db.Column(db.Date, default=date.today)
    hecha = db.Column(db.Boolean, default=False, index=True)

    cliente = db.relationship("Cliente", backref="tareas")
