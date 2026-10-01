# -*- coding: utf-8 -*-
"""Rutas web del Sistema de Cobros."""
import io
import os
import re
import sqlite3
import unicodedata
from datetime import date

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, jsonify, send_file, current_app, Response)

from .models import (db, Parametro, AnioCobro, GrupoFamiliar, Cliente,
                     PresupuestoCliente, CuentaCobro, CuentaLinea, Envio,
                     Ajuste, Pago, ESTADOS, TrabajoAdicional, saludo_de_cliente,
                     AsesoriaCatalogo, AsesoriaCliente, PresupuestoHistorial,
                     Tarea)
from .pdf_generator import generar_pdf, ruta_pdf
from . import rutas_comunes

bp = Blueprint("main", __name__)


def anio_actual():
    a = AnioCobro.query.filter_by(activo=True).first()
    if a is None:
        a = AnioCobro.query.order_by(AnioCobro.anio_cobro.desc()).first()
    return a


def _rebase(ruta):
    """Adapta rutas de OneDrive entre PCs (casa usa una letra, oficina otra).
    Si la ruta guardada no existe en este PC pero pasa por una carpeta OneDrive
    y existe el tramo equivalente bajo la raíz local de OneDrive, se reconstruye.
    Si no hay equivalente existente, se conserva la original (se creará allí)."""
    ruta = (ruta or "").strip()
    if not ruta:
        return ruta
    try:
        if os.path.isdir(ruta):
            return ruta
    except OSError:
        pass
    partes = [p for p in re.split(r"[\\/]+", ruta) if p]
    for i, p in enumerate(partes):
        if p.lower() == "onedrive":
            resto = partes[i + 1:]
            raices = [os.environ.get("OneDrive", ""),
                      os.environ.get("OneDriveConsumer", ""),
                      os.path.join(os.path.expanduser("~"), "OneDrive")]
            for raiz in [r for r in raices if r]:
                nueva = os.path.join(raiz, *resto)
                try:
                    if os.path.isdir(nueva):
                        return nueva
                except OSError:
                    pass
            break   # sin equivalente existente: no se especula
    return ruta


def _carpeta_pdfs():
    """Carpeta donde se guardan los PDF (Parámetros; defecto Documentos\\Cuentas de Cobro)."""
    carpeta = _rebase(Parametro.get("carpeta_pdfs", ""))
    if not carpeta:
        carpeta = _rebase(Parametro.get("carpeta_pdfs_envio", ""))
    if not carpeta:
        carpeta = os.path.join(os.path.expanduser("~"), "Documents", "Cuentas de Cobro")
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _carpeta_correos():
    """Carpeta solo para los borradores .eml (parametrizable e independiente)."""
    carpeta = _rebase(Parametro.get("carpeta_correos", ""))
    if not carpeta:
        return _carpeta_pdfs()
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _carpeta_imagenes():
    """Carpeta para las imágenes de cuentas (WhatsApp); parametrizable e independiente.
    Vacía = usa la carpeta de PDFs."""
    carpeta = _rebase(Parametro.get("carpeta_imagenes", ""))
    if not carpeta:
        return _carpeta_pdfs()
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


def _slug_archivo(s):
    """Nombre seguro para archivos: sin acentos ni caracteres raros."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_") or "cliente"


def _nombre_propio(s):
    """'Ochoa Velasquez Rafael': mayúscula inicial en nombres y apellidos, con
    partículas (de, del, la, y...) en minúscula salvo al inicio. Se aplica ANTES
    del slug para que los PDF/quedas se llamen Ochoa_Velasquez_Rafael_..."""
    particulas = {"de", "del", "la", "las", "los", "y", "e", "o", "u"}
    palabras = (s or "").strip().split()
    fuera = []
    for i, p in enumerate(palabras):
        if i > 0 and p.lower() in particulas:
            fuera.append(p.lower())
        else:
            fuera.append(p.capitalize())
    return " ".join(fuera)


def _nombre_pdf(cuenta):
    """Ochoa_Velasquez_Rafael_CdeC_26_001.pdf (pagador en nombre propio, luego CdeC + número)."""
    pag = cuenta.pagador_principal
    num = cuenta.numero_formateado.replace("-", "_")
    return f"{_slug_archivo(_nombre_propio(pag.nombre if pag else ''))}_CdeC_{num}.pdf"


def _numero_libre(a):
    """Consecutivo real: el primero que NO exista ya. Se autorepara si OneDrive
    dejó el contador atrasado (o si una copia de la BD llegó con cuentas nuevas)."""
    usados = {n for (n,) in db.session.query(CuentaCobro.numero)
              .filter(CuentaCobro.anio_cobro_id == a.id).all()}
    n = max(a.numero_siguiente or 1, a.consecutivo_inicial or 1)
    while n in usados:
        n += 1
    return n


def _primer_nombre(cli):
    """Primer nombre de pila del cliente (tras los 2 apellidos) para el saludo del correo."""
    if cli is None:
        return ""
    if (getattr(cli, "trato", "") or "").strip().upper() == "SRS":
        return ""
    saludo = saludo_de_cliente(cli)
    if saludo == "Señores":
        return ""                       # empresas / ambiguo: saludo sin nombre
    PARTICULAS = {"DE", "LA", "DEL", "LOS", "LAS", "SAN", "SANTA", "VON", "VAN", "DA", "DU"}
    palabras = [w.strip(".,;") for w in (cli.nombre or "").split() if w.strip(".,;")]
    palos = [w for w in palabras if w.upper() not in PARTICULAS]
    pila = palos[2:] if len(palos) > 2 else palos
    return (pila[0].title() if pila else "")


def _cuerpo_correo(cuenta, pagador, extra=""):
    """Cuerpo del correo (formato de la oficina). `extra` son líneas adicionales
    (ej. avisos de declaraciones adjuntas o trabajos). Multilínea => verbos en plural."""
    banco = (cuenta.anio.banco_info
             or Parametro.get("banco_info", "")).strip()
    extra = (extra or "").strip().replace("\r\n", "\n")
    plural = "\n" in extra          # varias líneas = cuentas/declaraciones múltiples
    nombre = _primer_nombre(pagador)
    saludo = f"Cordial saludo {nombre}," if nombre else "Cordial saludo,"
    # Declaración de renta SIEMPRE al inicio; en plural cuando es grupo familiar.
    # (De paso: números de cuenta SIN duplicar — antes repetía el mismo número.)
    lineas_act = [l for l in cuenta.lineas if l.estado == "ACTIVA"]
    familia = (bool(getattr(pagador, "grupo", None))
               or len({l.cliente_id for l in lineas_act}) > 1)
    decl = ("las declaraciones de renta presentadas" if familia
            else "la declaración de renta presentada")
    nums = sorted({l.cuenta.numero_formateado for l in lineas_act}) or [cuenta.numero_formateado]
    if len(nums) > 1:
        lista = ", ".join(nums[:-1]) + " y " + nums[-1]
        detalle = (f"Adjunto {decl} y las cuentas de cobro números {lista} "
                   "correspondientes a las asesorías prestadas este año.")
    elif familia:
        detalle = (f"Adjunto {decl} y la cuenta de cobro número {nums[0]} "
                   "correspondientes a las asesorías prestadas este año.")
    else:
        detalle = (f"Adjunto {decl} y la cuenta de cobro número {nums[0]} "
                   "correspondiente a la asesoría prestada este año.")
    if familia or plural:
        aviso = ("Tan pronto se efectúe el pago por favor nos notifican para asentar "
                 "la cancelación de las cuentas de cobro." if len(nums) > 1 else
                 "Tan pronto se efectúe el pago por favor nos notifican para asentar "
                 "la cancelación de la cuenta de cobro.")
    else:
        aviso = ("Tan pronto se efectúe el pago por favor nos notifica para asentar "
                 "la cancelación de la cuenta de cobro.")
    partes = [saludo, "", detalle]
    if extra:
        partes += [extra, ""]
    partes += ["Se puede consignar o Transferir en:", "", banco, "", aviso, "",
               "Cualquier inquietud con gusto la atenderemos."]
    return "\n".join(partes)


@bp.app_context_processor
def inject_helpers():
    def p(clave, defecto=""):
        return Parametro.get(clave, defecto)
    return dict(p=p, TrabajoAdicional=TrabajoAdicional)


# ---------------- Dashboard ----------------
@bp.route("/")
def dashboard():
    a = anio_actual()
    if not a:
        return render_template("sin_anio.html")
    presup = db.session.query(db.func.coalesce(db.func.sum(PresupuestoCliente.valor), 0.0))\
        .filter_by(anio_cobro=a.anio_cobro).scalar()
    emitido = db.session.query(db.func.coalesce(db.func.sum(CuentaLinea.valor), 0.0))\
        .join(CuentaCobro).filter(CuentaCobro.anio_cobro_id == a.id,
                                  CuentaLinea.estado == "ACTIVA",
                                  CuentaCobro.estado != "ANULADA").scalar()
    pagado = db.session.query(db.func.coalesce(db.func.sum(Pago.valor), 0.0))\
        .join(CuentaCobro).filter(CuentaCobro.anio_cobro_id == a.id,
                                  CuentaCobro.estado != "ANULADA").scalar()
    ajustes = db.session.query(db.func.coalesce(db.func.sum(Ajuste.valor), 0.0))\
        .join(CuentaCobro).filter(CuentaCobro.anio_cobro_id == a.id,
                                  CuentaCobro.estado != "ANULADA").scalar()

    # clientes con presupuesto > 0 sin línea activa en ninguna cuenta
    con_cuenta = {l.cliente_id for c in a.cuentas for l in c.lineas if l.estado == "ACTIVA"}
    sin_cuenta = []
    for p in PresupuestoCliente.query.filter_by(anio_cobro=a.anio_cobro).all():
        if p.cliente.activo and p.valor > 0 and p.cliente.id not in con_cuenta:
            sin_cuenta.append(p.cliente)
    sin_cuenta.sort(key=lambda c: c.nombre)

    cuentas = a.cuentas.order_by(CuentaCobro.numero).all()
    return render_template("dashboard.html", a=a, presup=presup, emitido=emitido,
                           pagado=pagado, ajustes=ajustes, cuentas=cuentas,
                           sin_cuenta=sin_cuenta)


# ---------------- Clientes ----------------
@bp.route("/clientes")
def clientes():
    ver = request.args.get("ver", "activos")
    query = Cliente.query
    if ver == "inactivos":
        query = query.filter_by(activo=False)
    else:
        query = query.filter_by(activo=True)
    lista = query.order_by(Cliente.nombre).all()
    if ver == "cobrables":
        lista = [c for c in lista if c.puede_cobrarse]
    # numero de orden en la vista (1..N) para la columna #: solo cuenta clientes visibles.
    # Orden alfabetico REAL (ignora tildes: SQLite pone 'Á' despues de 'Z').
    lista = sorted(lista, key=lambda c: unicodedata.normalize("NFD", (c.nombre or ""))
                   .encode("ascii", "ignore").decode().strip().lower())
    for _i, _c in enumerate(lista, 1):
        _c.num_orden = _i
    # tareas pendientes por cliente (para el aviso ⚠ en el nombre y el modulo Tareas)
    tpend = {}
    for t in Tarea.query.filter_by(hecha=False).order_by(Tarea.fecha.desc(), Tarea.id.desc()):
        tpend.setdefault(t.cliente_id, []).append(t)
    for c in lista:
        c.tareas_pend = tpend.get(c.id, [])
    a = anio_actual()
    presup = {}
    if a:
        for p in PresupuestoCliente.query.filter_by(anio_cobro=a.anio_cobro):
            presup[p.cliente_id] = p
        # estado de cobro por cliente (para pintar el nombre en el listado):
        # pagado > enviada > cobrada (cuenta existe) — según la cuenta más avanzada
        # donde el cliente tenga línea ACTIVA
        estados_cobro = {c.id: "cobrada" for c in Cliente.query.filter_by(activo=True)}
        c_ids = {c.id: c for c in CuentaCobro.query
                 .filter(CuentaCobro.anio_cobro_id == a.id,
                         CuentaCobro.estado != "ANULADA")
                 .order_by(CuentaCobro.id).all()}
        lin_por_cliente = {}
        for l in CuentaLinea.query.filter_by(estado="ACTIVA").all():
            cta = c_ids.get(l.cuenta_id)
            if cta:
                lin_por_cliente.setdefault(l.cliente_id, []).append(cta)
        for cli_id, ctas in lin_por_cliente.items():
            if any(c.estado == "PAGADA" and c.saldo <= 0 for c in ctas):
                estados_cobro[cli_id] = "pagada"
            elif any(c.estado in ("ENVIADA", "PAGADA") for c in ctas):
                estados_cobro[cli_id] = "enviada"
    else:
        estados_cobro = {}

    # pagado real del año por cliente: pagos de sus cuentas prorrateados
    # por el valor de cada línea (en grupos paga el pagador, cubre a todos)
    pagado_actual = {}
    if a:
        c_ids_p = {c.id: c for c in CuentaCobro.query
                   .filter(CuentaCobro.anio_cobro_id == a.id,
                           CuentaCobro.estado != "ANULADA").all()}
        lineas_por_cuenta = {}
        for l in CuentaLinea.query.filter_by(estado="ACTIVA").all():
            if l.cuenta_id in c_ids_p:
                lineas_por_cuenta.setdefault(l.cuenta_id, []).append(l)
        for pago in Pago.query.join(CuentaCobro).filter(
                CuentaCobro.anio_cobro_id == a.id,
                CuentaCobro.estado != "ANULADA").all():
            ls = lineas_por_cuenta.get(pago.cuenta_id, [])
            tot = sum(l.valor for l in ls)
            if tot <= 0:
                continue
            for l in ls:
                pagado_actual[l.cliente_id] = pagado_actual.get(l.cliente_id, 0.0) \
                    + pago.valor * (l.valor / tot)
    # correos (.eml) por cliente: los .eml se nombran SLUG-DEL-PAGADOR_CdeC_...,
    # así que un cliente tiene correo si SU slug (o el de un grupo donde es pagador) está
    n_correos = {}
    carpeta = _carpeta_correos()
    try:
        for fn in os.listdir(carpeta):
            if fn.lower().endswith(".eml"):
                n_correos[os.path.splitext(fn)[0].upper()] = True
    except OSError:
        pass
    correos = {}
    for cli in lista:
        slugs = [_slug_archivo(cli.nombre).upper()]
        if cli.es_pagador and cli.grupo:
            for m in cli.grupo.miembros:
                slugs.append(_slug_archivo(m.nombre).upper())
        n = sum(1 for k in n_correos if any(k.startswith(s + "_") for s in slugs))
        if n:
            correos[cli.id] = n
    # aviso visible: clientes sin obligaciones presentadas en el maestro (o sin NIT)
    maestro_check = {}
    if a and lista:
        from .maestro import leer_maestro
        nits_lista = {(c.nit or "").strip() for c in lista} - {""}
        m_check = leer_maestro(a.anio_cobro, a.anio_gravable, nits_lista) if nits_lista else {}
        for c in lista:
            n = (c.nit or "").strip()
            if not n:
                maestro_check[c.id] = "sin NIT"
            elif not (m_check or {}).get(n):
                maestro_check[c.id] = "no_encontrado"
    previo_todo = _filas_auditoria(a) if a else []
    previo_audit = [f for f in previo_todo if f["estado"] != "SIN_EMITIR"]
    previo_sin_emitir = len(previo_todo) - len(previo_audit)
    return render_template("clientes.html", clientes=lista, ver=ver,
                           presup=presup, a=a, correos=correos,
                           estados_cobro=estados_cobro, pagado_actual=pagado_actual,
                           maestro_check=maestro_check, previo_audit=previo_audit,
                           previo_sin_emitir=previo_sin_emitir,
                           grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre))


@bp.route("/clientes/importar-cobros-2025", methods=["POST"])
def clientes_importar_cobros_2025():
    """Lee el Excel del año anterior y guarda lo EFECTIVAMENTE cobrado por cliente."""
    from .cobros_2025 import leer_cobros_2025
    path = Parametro.get("excel_cobros_anterior", "") or rutas_comunes.excel_anterior_defecto()
    if not os.path.isfile(path):
        flash(f"No encontré el Excel del año anterior: {path}", "error")
        return redirect(url_for("main.clientes"))
    try:
        datos = leer_cobros_2025(path)
    except Exception as e:
        flash(f"No pude leer el Excel: {e}", "error")
        return redirect(url_for("main.clientes"))
    n = 0
    for cli in Cliente.query.all():
        v = datos.get(cli.codigo)
        if v:
            cli.cobrado_anterior_real = round(v)
            n += 1
    db.session.commit()
    flash(f"Pagos del año anterior actualizados para {n} clientes "
          f"(desde {os.path.basename(path)})", "ok")
    return redirect(url_for("main.clientes"))


@bp.route("/clientes/<int:cid>/cobrado-anterior", methods=["POST"])
def cliente_cobrado_anterior(cid):
    """Edita a mano lo EFECTIVAMENTE pagado del año anterior (primer llenado)."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    raw = (request.form.get("valor") or "").strip()
    try:
        cli.cobrado_anterior_real = float(raw) if raw else 0
    except ValueError:
        pass
    db.session.commit()
    return jsonify(ok=True, valor=float(cli.cobrado_anterior_real or 0))


@bp.route("/clientes/<int:cid>/cobrado-todo", methods=["POST"])
def cliente_cobrado_todo(cid):
    """Un clic: lo efectivamente pagado del año anterior = todo lo cobrado."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    pa = float(cli.cobrado_anterior or 0)
    if pa <= 0:
        return jsonify(ok=False, error="sin cobro registrado el año anterior")
    cli.cobrado_anterior_real = pa
    db.session.commit()
    return jsonify(ok=True, valor=pa)


@bp.route("/clientes/<int:cid>/photo-card")
def cliente_photo_card(cid):
    """Photo card: desglose imprimible de todo lo que se le está cobrando al cliente
    (para enviarle o mostrarle cuando la pida)."""
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    todas, _base_pc = _asesorias_filas(cli, a) if a else ([], 0.0)
    hay_maestro = any(f["en_maestro"] for f in todas)
    filas = [f for f in todas if f["incluir"]]
    excluidas = len(todas) - len(filas)
    total = sum(f["subtotal"] for f in filas)
    presup = 0.0
    if a:
        p = PresupuestoCliente.query.filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first()
        presup = float(p.valor or 0) if p else 0.0
    trabajos = cli.trabajos.order_by(TrabajoAdicional.fecha.desc(), TrabajoAdicional.id.desc()).all()
    return render_template("photo_card.html", cli=cli, a=a, filas=filas,
                           excluidas=excluidas, total=total, presup=presup,
                           hay_maestro=hay_maestro,
                           trabajos=trabajos, hoy=date.today(),
                           emisor=Parametro.get("emisor_nombre", ""))


@bp.route("/clientes/<int:cid>/moroso-cerrar", methods=["POST"])
def cliente_moroso_cerrar(cid):
    """Marca al deudor como NO moroso (acuerdo interno, descuento pactado...).
    La nota es OBLIGATORIA: es el rastro que queda en /morosos y en el Excel."""
    cli = db.get_or_404(Cliente, cid)
    nota = (request.form.get("nota") or "").strip()
    if not nota:
        return jsonify(ok=False, error="La nota es obligatoria para cerrar el moroso")
    cli.moroso_cerrado = True
    cli.moroso_nota = nota[:300]
    db.session.commit()
    return jsonify(ok=True)


@bp.route("/clientes/<int:cid>/moroso-reabrir", methods=["POST"])
def cliente_moroso_reabrir(cid):
    """Deshace el cierre: el cliente vuelve a la lista de morosos."""
    cli = db.get_or_404(Cliente, cid)
    cli.moroso_cerrado = False
    db.session.commit()
    return jsonify(ok=True)


@bp.route("/clientes/<int:cid>/moroso-nota", methods=["POST"])
def cliente_moroso_nota(cid):
    """Nota del módulo de morosos (historia del cliente con el cobro)."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    cli.moroso_nota = (request.form.get("nota") or "").strip()[:300]
    db.session.commit()
    return jsonify(ok=True)


@bp.route("/morosos")
def morosos():
    """Deudores del año anterior y clientes sin cobro registrado, para revisar
    uno a uno quién pagó, quién debe y a quién se le olvidó cobrar."""
    a = anio_actual()
    if not a:
        flash("No hay año activo", "error")
        return redirect(url_for("main.dashboard"))
    # pagado real del año actual por cliente (prorrateado entre líneas del grupo)
    pag_act = {}
    c_ids = {c.id: c for c in CuentaCobro.query
             .filter(CuentaCobro.anio_cobro_id == a.id,
                     CuentaCobro.estado != "ANULADA").all()}
    lin_cta = {}
    for l in CuentaLinea.query.filter_by(estado="ACTIVA").all():
        if l.cuenta_id in c_ids:
            lin_cta.setdefault(l.cuenta_id, []).append(l)
    for pago in Pago.query.join(CuentaCobro).filter(
            CuentaCobro.anio_cobro_id == a.id,
            CuentaCobro.estado != "ANULADA").all():
        ls = lin_cta.get(pago.cuenta_id, [])
        tot = sum(l.valor for l in ls)
        if tot <= 0:
            continue
        for l in ls:
            pag_act[l.cliente_id] = pag_act.get(l.cliente_id, 0.0) + pago.valor * (l.valor / tot)
    # estado del año actual por cliente (peor no: el mejor estado alcanzado)
    sev = {"BORRADOR": 1, "ENVIADA": 2, "PAGADA": 3}
    ETAQ = {0: ("sin cuenta", "light text-dark"), 1: ("BORRADOR", "secondary"),
            2: ("ENVIADA", "warning"), 3: ("PAGADA", "success")}
    est_cli = {}
    for cta_id, ls in lin_cta.items():
        cta = c_ids[cta_id]
        nivel = sev.get(cta.estado, 0)
        for l in ls:
            if nivel > est_cli.get(l.cliente_id, (0, ""))[0]:
                est_cli[l.cliente_id] = (nivel, cta.numero_formateado)
    estados = {cid_: ETAQ[n[0]] for cid_, n in est_cli.items()}
    niveles = {cid_: n[0] for cid_, n in est_cli.items()}

    presup = {p.cliente_id: p.valor for p in
              PresupuestoCliente.query.filter_by(anio_cobro=a.anio_cobro).all()}

    deudores, acuerdos, sin_cobro = [], [], []
    deuda_tot = 0.0
    descuento_tot = 0.0
    pag_ant_tot = 0.0
    for c in Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all():
        pa = float(c.cobrado_anterior or 0)        # lo que se le cobró el año pasado
        ef = float(c.cobrado_anterior_real or 0)   # lo que realmente pagó el año pasado
        pag_ant_tot += ef
        if pa > 0 and ef < pa - 0.5:
            falta = pa - ef
            if c.moroso_cerrado:
                # acuerdo interno / descuento pactado: no es moroso, pero deja rastro
                acuerdos.append((c, pa, ef, falta, estados.get(c.id, ETAQ[0])))
                descuento_tot += falta
            else:
                deudores.append((c, pa, ef, falta, pag_act.get(c.id, 0.0), estados.get(c.id, ETAQ[0])))
                deuda_tot += falta
        elif pa == 0:
            sin_cobro.append((c, pag_act.get(c.id, 0.0), estados.get(c.id, ETAQ[0])))
    sin_cobro.sort(key=lambda t: (niveles.get(t[0].id, 0) != 0, t[0].nombre))  # sin cuenta 2026 primero
    return render_template("morosos.html", a=a, deudores=deudores, acuerdos=acuerdos,
                           sin_cobro=sin_cobro, deuda_tot=deuda_tot,
                           descuento_tot=descuento_tot, pag_ant_tot=pag_ant_tot,
                           n_sin=len(sin_cobro), presup=presup)


@bp.route("/clientes/<int:cid>/correo")
def cliente_correo(cid):
    """Redactar correo desde el listado: MISMA función que el botón 'Redactar correo'
    de la cuenta. Toma la cuenta vigente del cliente (la más reciente no anulada),
    genera PDF + .eml de borrador de Outlook y lo descarga al instante (también
    queda en la carpeta de correos). Sin cuenta que cobrar → avisa."""
    cli = db.get_or_404(Cliente, cid)
    destino = request.referrer or url_for("main.clientes")
    a = anio_actual()
    cuenta = None
    if a:
        # la cuenta vigente: la más reciente no anulada donde el cliente tiene línea ACTIVA
        lin = (CuentaLinea.query
               .filter(CuentaLinea.cliente_id == cli.id, CuentaLinea.estado == "ACTIVA")
               .join(CuentaCobro)
               .filter(CuentaCobro.anio_cobro_id == a.id, CuentaCobro.estado != "ANULADA")
               .order_by(CuentaCobro.id.desc()).first())
        cuenta = lin.cuenta if lin else None
    if not cuenta:
        msg = (f"{cli.nombre} no tiene cuenta de cobro por cobrar este año. "
               f"Primero genera la cuenta (rayo ⚡ o desde su detalle).")
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=False, error=msg)
        flash(msg, "error")
        return redirect(destino)
    pagador = cuenta.pagador_principal
    if not pagador or not (pagador.email or "").strip():
        msg = (f"El pagador {pagador.nombre if pagador else '(sin pagador)'} no tiene correo "
               f"guardado en su ficha. Regístralo y vuelve a intentar.")
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=False, error=msg)
        flash(msg, "error")
        return redirect(destino)
    carpeta = _carpeta_correos()
    ruta_eml = _generar_eml(cuenta, carpeta)
    if cuenta.estado == "BORRADOR":
        cuenta.estado = "ENVIADA"
    if not cuenta.envios.first():
        db.session.add(Envio(cuenta_id=cuenta.id, medio="Correo", fecha=date.today(),
                             nota=f"Borrador .eml generado en {carpeta} (para {pagador.email})"))
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, nombre=os.path.basename(ruta_eml),
                       mensaje=f"PDF y borrador de correo listos en {carpeta}")
    return send_file(ruta_eml, as_attachment=True,
                     download_name=os.path.basename(ruta_eml))


@bp.route("/clientes/<int:cid>/imagen", methods=["GET", "POST"])
def cliente_imagen(cid):
    """Imagen PNG de la cuenta (para WhatsApp) desde el listado: la guarda en la
    carpeta de imagenes parametrizada (Parametros) y TAMBIEN la descarga al
    navegador, lista para adjuntar. Por fetch NO recarga la pagina (blob);
    sin JS, redirige con flash."""
    from .imagen_cuenta import generar_imagen, _nombre_imagen
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    cuenta = None
    if a:
        lin = (CuentaLinea.query
               .filter(CuentaLinea.cliente_id == cli.id, CuentaLinea.estado == "ACTIVA")
               .join(CuentaCobro)
               .filter(CuentaCobro.anio_cobro_id == a.id, CuentaCobro.estado != "ANULADA")
               .order_by(CuentaCobro.id.desc()).first())
        cuenta = lin.cuenta if lin else None
    destino = request.referrer or url_for("main.clientes")
    if not cuenta:
        msg = (f"{cli.nombre} no tiene cuenta de cobro este año. "
               f"Primero genera la cuenta (rayo ⚡ o desde su detalle).")
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=False, error=msg)
        flash(msg, "error")
        return redirect(destino)
    carpeta = _carpeta_imagenes()
    ruta = os.path.join(carpeta, _nombre_imagen(cuenta))
    generar_imagen(cuenta, ruta)
    if request.accept_mimetypes.best == "application/json":
        # guarda en carpeta Y descarga al navegador (blob), sin recargar
        resp = send_file(ruta, as_attachment=True,
                         download_name=os.path.basename(ruta))
        resp.headers["X-Nombre"] = os.path.basename(ruta)
        resp.headers["X-Mensaje"] = "Imagen descargada y guardada en la carpeta de imagenes"
        return resp
    flash(f"Imagen guardada en: {ruta}", "ok")
    return redirect(destino)


@bp.route("/clientes/<int:cid>/decl", methods=["POST"])
def cliente_decl(cid):
    """Scanner de declaraciones: con select guarda ese valor; sin él, cicla al siguiente."""
    cli = db.get_or_404(Cliente, cid)
    vals = ("", "NO_OBLIGADO", "PRESENTADA")
    nuevo = request.form.get("decl")
    if nuevo in vals:
        cli.decl_renta = nuevo
    else:
        actual = cli.decl_renta if cli.decl_renta in vals else ""
        cli.decl_renta = vals[(vals.index(actual) + 1) % 3]
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, decl=cli.decl_renta, cobrable=cli.puede_cobrarse,
                       estado=cli.estado_cobro_grupo)
    flash(f"{cli.nombre}: {Cliente.DECL_ETIQUETAS.get(cli.decl_renta, cli.decl_renta)}", "ok")
    return redirect(request.referrer or url_for("main.clientes"))


@bp.route("/clientes/<int:cid>/email-rapido", methods=["POST"])
def cliente_email_rapido(cid):
    """Guarda/corrige el email del cliente desde el listado (sin abrir la ficha).
    Por fetch responde JSON: la pagina NO se recarga y se conserva el lugar."""
    cli = db.get_or_404(Cliente, cid)
    email = (request.form.get("email") or "").strip().lower()
    if email and ("@" not in email or "." not in email.split("@")[-1]):
        msg = f"Correo no válido: {email or '(vacío)'}"
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=False, error=msg)
        flash(msg, "error")
        return redirect(request.referrer or url_for("main.clientes"))
    cli.email = email
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, email=cli.email,
                       mensaje=f"correo guardado: {cli.email or '(borrado)'}")
    flash(f"{cli.nombre}: correo guardado ({cli.email or 'borrado'})", "ok")
    return redirect(request.referrer or url_for("main.clientes"))


@bp.route("/clientes/<int:cid>/decl-maestro", methods=["POST"])
def cliente_decl_maestro(cid):
    """Importa el estado de la renta AG-2025 desde el Sistema Maestro
    (obligaciones RENTA con scanner_estado='PRESENTADA'). Si el cliente es de
    grupo, revisa a todo el grupo (cubre el caso empresa PJ + familiares)."""
    cli = db.get_or_404(Cliente, cid)
    ruta = _ruta_maestro_activa()
    if not ruta or not os.path.isdir(ruta):
        flash("Configura la carpeta del Sistema Maestro en Parámetros (Carpeta del Sistema Maestro).", "error")
        return redirect(request.referrer or url_for("main.clientes"))
    db_maestro = os.path.join(ruta, "data", "sistema_maestro_v4.db")
    if not os.path.isfile(db_maestro):
        flash(f"No encontré la BD del maestro: {db_maestro}", "error")
        return redirect(request.referrer or url_for("main.clientes"))
    con = sqlite3.connect(db_maestro)
    try:
        filas = con.execute(
            "SELECT nit FROM obligaciones "
            "WHERE impuesto LIKE 'RENTA%' AND periodo LIKE 'AG-2025%' "
            "AND scanner_estado = 'PRESENTADA' AND nit IS NOT NULL").fetchall()
    finally:
        con.close()
    nits = {str(n[0]).strip() for n in filas if n[0]}
    if cli.grupo_id:
        objetivo = [m for m in cli.grupo.miembros if m.activo]
    else:
        objetivo = [cli]
    tocados = []
    for m in objetivo:
        if (m.nit or "").strip() in nits and m.decl_renta != "PRESENTADA":
            m.decl_renta = "PRESENTADA"
            tocados.append(m.nombre)
    db.session.commit()
    if tocados:
        flash(f"Maestro: marcadas PRESENTADA las rentas de: {', '.join(tocados)}.", "ok")
    else:
        flash(f"El maestro no tiene renta AG-2025 presentada para {'el grupo de ' + cli.nombre if cli.grupo_id else cli.nombre}.", "error")
    return redirect(request.referrer or url_for("main.clientes"))


@bp.route("/clientes/sync-maestro", methods=["POST"])
def clientes_sync_maestro():
    """Trae del Sistema Maestro las rentas AG-2025 que su scanner ya marcó como
    PRESENTADA y actualiza a todos los clientes de una vez (cruce por NIT)."""
    ruta = _ruta_maestro_activa()
    if not ruta or not os.path.isdir(ruta):
        flash("Configura la carpeta del Sistema Maestro en Parámetros.", "error")
        return redirect(request.referrer or url_for("main.clientes"))
    db_maestro = os.path.join(ruta, "data", "sistema_maestro_v4.db")
    if not os.path.isfile(db_maestro):
        flash(f"No encontré la BD del maestro: {db_maestro}", "error")
        return redirect(request.referrer or url_for("main.clientes"))
    con = sqlite3.connect(db_maestro)
    try:
        filas = con.execute(
            "SELECT nit FROM obligaciones "
            "WHERE impuesto LIKE 'RENTA%' AND periodo LIKE 'AG-2025%' "
            "AND scanner_estado = 'PRESENTADA' AND nit IS NOT NULL").fetchall()
    finally:
        con.close()
    nits = {str(n[0]).strip() for n in filas if n[0]}
    tocados = 0
    for cli in Cliente.query.all():
        if (cli.nit or "").strip() in nits and cli.decl_renta != "PRESENTADA":
            cli.decl_renta = "PRESENTADA"
            tocados += 1
    db.session.commit()
    flash(f"Maestro: {tocados} cliente(s) quedaron con renta PRESENTADA (cruce por NIT).", "ok")
    return redirect(request.referrer or url_for("main.clientes"))


def _cobrado_pagado_anterior(a, ids_cli):
    """(cobrado, pagado, anio) del año inmediatamente anterior para los clientes
    ids_cli: suma de sus lineas activas menos ajustes prorrateados, y lo
    efectivamente pagado (limitado a lo cobrado). Solo cuentas no anuladas."""
    anterior = (AnioCobro.query.filter(AnioCobro.anio_cobro < a.anio_cobro)
                .order_by(AnioCobro.anio_cobro.desc()).first())
    cob = pag = 0.0
    if anterior and ids_cli:
        for cu in (CuentaCobro.query.filter_by(anio_cobro_id=anterior.id)
                   .filter(CuentaCobro.estado != "ANULADA").all()):
            ls = [l for l in cu.lineas if l.estado == "ACTIVA" and l.cliente_id in ids_cli]
            if not ls:
                continue
            tot = sum(float(l.valor or 0) for l in ls)
            aj = float(cu.total_ajustes or 0)
            cob += max(tot - aj, 0.0)
            pag += min(float(cu.total_pagado or 0), max(tot - aj, 0.0))
    anio = anterior.anio_cobro if anterior else None
    return cob, pag, anio


def _lineas_previstas(cli, a):
    """(miembros_con_valores, es_grupo) tal como los crearia cuenta-expresa.
    Lanza ValueError con el mensaje del bloqueo si no se puede crear."""
    if cli.es_pagador and cli.grupo_id:
        miembros = [m for m in cli.grupo.miembros if m.activo]
    else:
        miembros = [cli]
    lineas = []
    for m in miembros:
        p = PresupuestoCliente.query.filter_by(cliente_id=m.id, anio_cobro=a.anio_cobro).first()
        if not p or p.valor <= 0:
            raise ValueError(f"{m.nombre} no tiene presupuesto {a.anio_cobro}.")
        lineas.append((m, float(p.valor)))
    return lineas, len(miembros) > 1


@bp.route("/clientes/<int:cid>/previsualizar-pdf", methods=["GET"])
def cliente_previsualizar_pdf(cid):
    """Preliminar del PDF SIN crear nada: mismos datos que usaria cuenta-expresa,
    con el numero que tomaria la cuenta. Devuelve el PDF en memoria (BytesIO)."""
    a = anio_actual()
    if not a:
        return "No hay año activo", 404
    cli = db.get_or_404(Cliente, cid)
    ya = (CuentaLinea.query.join(CuentaCobro)
          .filter(CuentaLinea.cliente_id == cli.id,
                  CuentaCobro.anio_cobro_id == a.id,
                  CuentaLinea.estado == "ACTIVA",
                  CuentaCobro.estado != "ANULADA").first())
    if ya:
        return (f"Este cliente ya está en la cuenta {ya.cuenta.numero_formateado}. "
                "No hay nada que previsualizar.", 409)
    try:
        lineas, es_grupo = _lineas_previstas(cli, a)
    except ValueError as e:
        return str(e), 409
    from io import BytesIO
    from .pdf_generator import datos_preview, generar_desde_dict
    d = datos_preview(a,
                      [{"nombre": m.nombre, "concepto": "", "valor": v} for m, v in lineas],
                      cli)
    d["numero"] = f"{a.prefijo}-{_numero_libre(a):03d}"   # el mismo que tomara la cuenta real
    buf = BytesIO()
    generar_desde_dict(d, buf)
    buf.seek(0)
    return send_file(buf, mimetype="application/pdf",
                     download_name=f"Preliminar_{cli.nombre.replace(' ', '_')}.pdf",
                     as_attachment=False)


@bp.route("/clientes/<int:cid>/cuenta-expresa", methods=["POST"])
def cliente_cuenta_expresa(cid):
    """Un clic: crea la cuenta con lo presupuestado (a toda la familia si el cliente
    es pagador de grupo) y guarda el PDF en la carpeta de Parámetros.
    Por fetch (listado) responde JSON: toast en pantalla y la pagina NO se recarga."""
    a = anio_actual()
    cli = db.get_or_404(Cliente, cid)
    destino = request.referrer or url_for("main.clientes")

    def _res(msg, tipo="ok"):
        if request.accept_mimetypes.best == "application/json":
            if tipo == "ok":
                return jsonify(ok=True, mensaje=msg)
            return jsonify(ok=False, error=msg)
        flash(msg, tipo)
        return redirect(destino)

    if not a:
        return _res("No hay año activo", "error")
    ya = (CuentaLinea.query.join(CuentaCobro)
          .filter(CuentaLinea.cliente_id == cli.id,
                  CuentaCobro.anio_cobro_id == a.id,
                  CuentaLinea.estado == "ACTIVA",
                  CuentaCobro.estado != "ANULADA").first())
    if ya:
        # ya esta en una cuenta BORRADOR sin .eml -> completala: PDF + borrador de Outlook
        yacuenta = ya.cuenta
        if yacuenta.estado == "BORRADOR" and not yacuenta.envios.first():
            pagador = yacuenta.pagador_principal
            if pagador and (pagador.email or "").strip():
                ccorreos = _carpeta_correos()
                _generar_eml(yacuenta, ccorreos)
                db.session.add(Envio(cuenta_id=yacuenta.id, medio="Correo", fecha=date.today(),
                                     nota=f"Borrador .eml generado en {ccorreos} (para {pagador.email})"))
                yacuenta.estado = "ENVIADA"
                db.session.commit()
                return _res(f"{cli.nombre} ya estaba en la cuenta {yacuenta.numero_formateado} (BORRADOR). "
                            f"La completé: PDF y borrador de Outlook (.eml) listos en {ccorreos}")
            return _res(f"{cli.nombre} ya está en la cuenta BORRADOR {yacuenta.numero_formateado}, "
                        f"pero el pagador no tiene correo guardado en su ficha.", "error")
        sobre = " (con borrador de Outlook ya generado: usa el sobre \u2709\ufe0f)" if yacuenta.envios.first() else ""
        return _res(f"{cli.nombre} ya está en la cuenta {yacuenta.numero_formateado} de este año{sobre}", "error")
    miembros = ([m for m in cli.grupo.miembros if m.activo]
                if cli.es_pagador and cli.grupo_id else [cli])
    lineas = []
    for m in miembros:
        p = PresupuestoCliente.query.filter_by(cliente_id=m.id, anio_cobro=a.anio_cobro).first()
        if not p or p.valor <= 0:
            return _res(f"{m.nombre} no tiene presupuesto {a.anio_cobro}. Cuenta no creada.", "error")
        lineas.append((m, p.valor))
    cuenta = CuentaCobro(anio_cobro_id=a.id, numero=_numero_libre(a),
                         fecha=date.today(), estado="BORRADOR")
    cuenta.pagador_cliente_id = cli.id
    db.session.add(cuenta)
    db.session.flush()
    for m, v in lineas:
        db.session.add(CuentaLinea(cuenta=cuenta, cliente_id=m.id, valor=v))
    a.numero_siguiente = cuenta.numero + 1
    db.session.commit()
    carpeta = _carpeta_pdfs()
    ruta = os.path.join(carpeta, _nombre_pdf(cuenta))
    generar_pdf(cuenta, ruta)
    total = sum(v for _, v in lineas)
    # expreso completo: si el pagador tiene correo, deja tambien el borrador .eml listo
    pagador = cuenta.pagador_principal
    base = f"Cuenta {cuenta.numero_formateado} creada ($ {total:,.0f}) y PDF en: {ruta}"
    if pagador and (pagador.email or "").strip():
        ccorreos = _carpeta_correos()
        _generar_eml(cuenta, ccorreos)
        db.session.add(Envio(cuenta_id=cuenta.id, medio="Correo", fecha=date.today(),
                             nota=f"Borrador .eml generado en {ccorreos} (para {pagador.email})"))
        cuenta.estado = "ENVIADA"
        db.session.commit()
        return _res(base + f". Borrador de Outlook (.eml) listo en {ccorreos}")
    return _res(base + ". El pagador no tiene correo guardado: solo quedó el PDF.")


@bp.route("/clientes/<int:cid>/trabajo-nuevo", methods=["POST"])
def cliente_trabajo_nuevo(cid):
    """Registra un trabajo adicional hecho al cliente (requerimiento, consulta, etc.)."""
    cli = db.get_or_404(Cliente, cid)
    desc = (request.form.get("descripcion") or "").strip()
    if not desc:
        flash("Describe el trabajo adicional", "error")
    else:
        a = anio_actual()
        val = (request.form.get("valor") or "").strip().replace(".", "").replace(",", ".")
        try:
            val = float(val) if val else 0.0
        except ValueError:
            val = 0.0
        db.session.add(TrabajoAdicional(
            cliente_id=cli.id, descripcion=desc, valor=val,
            anio_cobro=a.anio_cobro if a else date.today().year))
        db.session.commit()
        flash(f"Trabajo adicional registrado para {cli.nombre}", "ok")
    return redirect(request.referrer or url_for("main.cliente_detalle", cid=cid))


@bp.route("/trabajos/<int:tid>/estado", methods=["POST"])
def trabajo_estado(tid):
    """Cicla PENDIENTE -> COBRADO -> PENDIENTE (o fija con select)."""
    t = db.get_or_404(TrabajoAdicional, tid)
    nuevo = request.form.get("estado")
    if nuevo in ("PENDIENTE", "COBRADO"):
        t.estado = nuevo
    else:
        t.estado = "PENDIENTE" if t.estado == "COBRADO" else "COBRADO"
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, estado=t.estado)
    return redirect(request.referrer or url_for("main.cliente_detalle", cid=t.cliente_id))


@bp.route("/trabajos/<int:tid>/eliminar", methods=["POST"])
def trabajo_eliminar(tid):
    t = db.get_or_404(TrabajoAdicional, tid)
    cid = t.cliente_id
    db.session.delete(t)
    db.session.commit()
    flash("Trabajo adicional eliminado", "ok")
    return redirect(request.referrer or url_for("main.cliente_detalle", cid=cid))


@bp.route("/grupos/<int:gid>/cuenta-expresa", methods=["POST"])
def grupo_cuenta_expresa(gid):
    """Un clic desde Grupos: crea la cuenta de todo el grupo (miembros activos
    con presupuesto) a nombre del pagador del grupo, y deja el PDF en la carpeta."""
    a = anio_actual()
    g = db.get_or_404(GrupoFamiliar, gid)
    destino = request.referrer or url_for("main.grupos")
    if not a:
        flash("No hay año activo", "error")
        return redirect(destino)
    miembros = [m for m in g.miembros if m.activo]
    if not miembros:
        flash(f"El grupo {g.nombre} no tiene miembros activos", "error")
        return redirect(destino)
    ya = (CuentaLinea.query.join(CuentaCobro)
          .filter(CuentaLinea.cliente_id.in_([m.id for m in miembros]),
                  CuentaCobro.anio_cobro_id == a.id,
                  CuentaLinea.estado == "ACTIVA",
                  CuentaCobro.estado != "ANULADA").first())
    if ya:
        flash(f"Algún miembro del grupo ya está en la cuenta {ya.cuenta.numero_formateado} de este año", "error")
        return redirect(destino)
    lineas = []
    for m in miembros:
        p = PresupuestoCliente.query.filter_by(cliente_id=m.id, anio_cobro=a.anio_cobro).first()
        if not p or p.valor <= 0:
            flash(f"{m.nombre} no tiene presupuesto {a.anio_cobro}. Cuenta no creada.", "error")
            return redirect(destino)
        lineas.append((m, p.valor))
    pagador = g.pagador or miembros[0]
    cuenta = CuentaCobro(anio_cobro_id=a.id, numero=_numero_libre(a),
                         fecha=date.today(), estado="BORRADOR")
    cuenta.pagador_cliente_id = pagador.id
    db.session.add(cuenta)
    db.session.flush()
    for m, v in lineas:
        db.session.add(CuentaLinea(cuenta=cuenta, cliente_id=m.id, valor=v))
    a.numero_siguiente = cuenta.numero + 1
    db.session.commit()
    carpeta = _carpeta_pdfs()
    ruta = os.path.join(carpeta, _nombre_pdf(cuenta))
    generar_pdf(cuenta, ruta)
    total = sum(v for _, v in lineas)
    # expreso completo: si el pagador tiene correo, deja también el borrador .eml listo
    pagador = cuenta.pagador_principal
    base = f"Cuenta {cuenta.numero_formateado} del grupo {g.nombre} creada ($ {total:,.0f}) y PDF en: {ruta}"
    if pagador and (pagador.email or "").strip():
        ccorreos = _carpeta_correos()
        _generar_eml(cuenta, ccorreos)
        db.session.add(Envio(cuenta_id=cuenta.id, medio="Correo", fecha=date.today(),
                             nota=f"Borrador .eml generado en {ccorreos} (para {pagador.email})"))
        cuenta.estado = "ENVIADA"
        db.session.commit()
        flash(base + f". Borrador de Outlook (.eml) listo en {ccorreos}", "ok")
    else:
        flash(base + ". El pagador no tiene correo guardado: solo quedó el PDF.", "ok")
    return redirect(destino)


@bp.route("/clientes/nuevo", methods=["GET", "POST"])
def cliente_nuevo():
    a = anio_actual()
    if request.method == "POST":
        f = request.form
        codigo_max = db.session.query(db.func.max(Cliente.codigo)).scalar() or 0
        raw_cod = (f.get("codigo") or "").strip()
        try:
            codigo = int(raw_cod) if raw_cod else codigo_max + 1
        except ValueError:
            flash("El código debe ser numérico", "error")
            return render_template("cliente_form.html", cli=None, a=a,
                                   codigo_sugerido=codigo_max + 1,
                                   grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre)), 400
        if db.session.query(Cliente.id).filter_by(codigo=codigo).first():
            flash(f"El código {codigo} ya existe: cliente no creado (revise el número)", "error")
            return render_template("cliente_form.html", cli=None, a=a,
                                   codigo_sugerido=codigo_max + 1,
                                   grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre)), 400
        cli = Cliente(
            codigo=codigo,
            nombre=f["nombre"].strip().upper(),
            tipo=f.get("tipo", "PN"),
            trato=f.get("trato", "") if f.get("trato") in ("", "SR", "SRA") else "",
            nit=f.get("nit", "").strip(),
            dv=f.get("dv", "").strip(),
            ciudad=f.get("ciudad", "MEDELLÍN").strip() or "MEDELLÍN",
            direccion=f.get("direccion", "").strip(),
            telefonos=f.get("telefonos", "").strip(),
            email=f.get("email", "").strip(),
            grupo_id=int(f["grupo_id"]) if f.get("grupo_id") else None,
            nota=f.get("nota", "").strip(),
        )
        db.session.add(cli)
        db.session.flush()
        if a:
            db.session.add(PresupuestoCliente(cliente_id=cli.id, anio_cobro=a.anio_cobro,
                                              valor=float(f.get("valor") or 0)))
        db.session.commit()
        flash("Cliente creado", "ok")
        return redirect(url_for("main.clientes"))
    codigo_max = db.session.query(db.func.max(Cliente.codigo)).scalar() or 0
    return render_template("cliente_form.html", cli=None, a=a,
                           codigo_sugerido=codigo_max + 1,
                           grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre))


@bp.route("/clientes/<int:cid>")
def cliente_detalle(cid):
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    presup = PresupuestoCliente.query.filter_by(cliente_id=cid).all()
    lineas = CuentaLinea.query.filter_by(cliente_id=cid).all()
    historial = []
    for l in lineas:
        c = l.cuenta
        historial.append({
            "anio": c.anio.anio_cobro, "numero": c.numero_formateado, "cuenta_id": c.id,
            "fecha": c.fecha, "valor": l.valor, "estado_cuenta": c.estado,
            "estado_linea": l.estado,
            "pagos": [{"fecha": p.fecha, "valor": p.valor, "forma": p.forma} for p in c.pagos],
            "ajustes": sum(x.valor for x in c.ajustes),
            "total": c.total, "saldo": c.saldo,
            "envios": [{"fecha": e.fecha, "medio": e.medio} for e in c.envios],
        })
    historial.sort(key=lambda h: (h["anio"], h["numero"]))
    filas_asesorias, base_asesorias = _asesorias_filas(cli, a)
    total_asesorias = sum(fx["subtotal"] for fx in filas_asesorias)
    presup_act = next((p.valor for p in presup if p.anio_cobro == (a.anio_cobro if a else None)), 0)
    import json as _json
    datos_js = {
        "base": float(base_asesorias or 0),
        "presup": float(presup_act or 0),
        "renta_base": float(cli.renta_base or 0),
        "filas": [{"id": fx["it"].id, "nombre": fx["it"].nombre, "fija": bool(fx["fija"]),
                   "pct": fx["pct"], "valor": fx["valor"], "cantidad": fx["cantidad"],
                   "incluir": bool(fx["incluir"]),
                   "std_pct": float(fx["it"].defecto_pct or 0),
                   "std_val": float(fx["it"].defecto_valor or 0),
                   "base_min": (fx["it"].base_min or ""),
                   "en_maestro": bool(fx["en_maestro"])} for fx in filas_asesorias],
    }
    if cli.es_pagador and cli.grupo_id:
        ids_ant = [m.id for m in cli.grupo.miembros if m.activo]
    else:
        ids_ant = [cli.id]
    cob_ant, pag_ant, anio_ant = (_cobrado_pagado_anterior(a, ids_ant) if a
                                  else (0.0, 0.0, None))
    return render_template("cliente_detalle.html", cli=cli, presup=presup,
                           resumen_ant={"cobrado": cob_ant, "pagado": pag_ant,
                                        "anio": anio_ant},
                           datos_asesorias=_json.dumps(datos_js),
                           historial=historial, a=a,
                           filas_asesorias=filas_asesorias,
                           total_asesorias=total_asesorias,
                           base_asesorias=base_asesorias,
                           presup_act=presup_act or 0,
                           grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre))


@bp.route("/clientes/<int:cid>/presupuesto-guardar", methods=["POST"])
def cliente_presupuesto_guardar(cid):
    """Cambia el presupuesto del año activo CON motivo obligatorio. Registra el
    historial y aplica la regla de cuentas:
      - BORRADOR (o sin cuenta): regenera el PDF de las cuentas borrador del cliente.
      - ENVIADA / PAGADA: NO toca el PDF; deja nota interna en cada cuenta afectada.
    Devuelve JSON con el resultado para la ficha."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    valor_raw = (request.form.get("valor") or "").strip()
    motivo = (request.form.get("motivo") or "").strip()
    try:
        nuevo = float(valor_raw) if valor_raw else 0.0
    except ValueError:
        return jsonify(ok=False, error="Valor inválido")
    if not motivo:
        return jsonify(ok=False, error="El motivo es obligatorio para cambiar el presupuesto")
    p = PresupuestoCliente.query.filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first()
    if p is None:
        p = PresupuestoCliente(cliente_id=cid, anio_cobro=a.anio_cobro, valor=0.0)
        db.session.add(p)
    anterior = float(p.valor or 0)
    if abs(nuevo - anterior) < 0.5:
        return jsonify(ok=False, error="El valor es igual al actual")
    p.valor = nuevo
    db.session.add(PresupuestoHistorial(cliente_id=cid, anio_cobro=a.anio_cobro,
                                        valor_anterior=anterior, valor_nuevo=nuevo,
                                        motivo=motivo[:300], fecha=date.today()))
    # ---- cuentas del cliente en el año activo ----
    regenerados, marcadas = [], []
    lineas_cli = (CuentaLinea.query.filter_by(cliente_id=cid, estado="ACTIVA").all())
    cuentas = []
    for l in lineas_cli:
        cta = l.cuenta
        if cta.anio_cobro_id == a.id and cta.estado != "ANULADA" and cta not in cuentas:
            cuentas.append(cta)
    for cta in cuentas:
        if cta.estado == "BORRADOR" and cta.envios.count() == 0:
            carpeta = _carpeta_pdfs()
            generar_pdf(cta, os.path.join(carpeta, _nombre_pdf(cta)))
            regenerados.append(cta.numero_formateado)
        elif cta.estado in ("ENVIADA", "PAGADA") or cta.envios.count() > 0:
            nota = (f"Error en el cálculo de la cuenta. Valor real de servicios {a.anio_cobro}: "
                    f"$ {nuevo:,.0f} (presupuesto anterior: $ {anterior:,.0f}). "
                    f"Motivo: {motivo[:200]}. Ver photo card en cliente.")
            cta.observaciones = ((cta.observaciones or "") + "\n" + nota).strip()
            marcadas.append(cta.numero_formateado)
    db.session.commit()
    return jsonify(ok=True, anterior=anterior, nuevo=nuevo,
                   regenerados=regenerados, marcadas=marcadas,
                   mensaje=(f"Presupuesto {a.anio_cobro}: $ {anterior:,.0f} -> $ {nuevo:,.0f}. "
                            + (f"PDF regenerado: {', '.join(regenerados)}. " if regenerados else "")
                            + (f"NOTA interna dejada en: {', '.join(marcadas)}. " if marcadas else "")
                            + f"Motivo registrado: {motivo[:80]}"))


@bp.route("/clientes/<int:cid>/presupuesto-historial")
def cliente_presupuesto_historial(cid):
    """Filas del historial de presupuesto del cliente (para la ficha)."""
    from flask import jsonify
    hist = (PresupuestoHistorial.query.filter_by(cliente_id=cid)
            .order_by(PresupuestoHistorial.fecha.desc(), PresupuestoHistorial.id.desc()).limit(30).all())
    return jsonify(ok=True, filas=[{"fecha": h.fecha.strftime("%d/%m/%Y"),
                                    "anio": h.anio_cobro,
                                    "anterior": h.valor_anterior, "nuevo": h.valor_nuevo,
                                    "motivo": h.motivo} for h in hist])


@bp.route("/clientes/<int:cid>/asesorias-maestro", methods=["POST"])
def cliente_asesorias_maestro(cid):
    """Trae del maestro lo PRESENTADO del cliente (boton de la ficha).
    Marca/incluye las asesorias presentadas; no pisa % ni valores editados."""
    from flask import jsonify
    from .maestro import leer_maestro
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    nit = (cli.nit or "").strip()
    if not nit:
        return jsonify(ok=False, error="El cliente no tiene NIT guardado")
    m = leer_maestro(a.anio_cobro, a.anio_gravable, {nit}) or {}
    bruto = m.get(nit) or {}
    cod2id = {c.codigo: c.id for c in AsesoriaCatalogo.query.all()}
    datos = {cod2id[k]: v for k, v in bruto.items() if k in cod2id}
    if not datos:
        return jsonify(ok=False, encontrado=False,
                       error="El maestro no muestra obligaciones presentadas para el NIT %s" % nit)
    agregadas, ya = [], []
    for aid in datos:
        it = db.session.get(AsesoriaCatalogo, aid)
        if not it or not it.activo:
            continue
        if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
            continue
        x = AsesoriaCliente.query.filter_by(cliente_id=cid, asesoria_id=aid).first()
        if x is None:
            x = AsesoriaCliente(cliente_id=cid, asesoria_id=aid, incluir=True)
            if it.es_fija:
                x.cantidad = max(1, datos[aid][0])
            db.session.add(x)
            agregadas.append(it.nombre)
        elif not x.incluir:
            x.incluir = True
            if it.es_fija:
                x.cantidad = max(1, datos[aid][0])
            agregadas.append(it.nombre)
        else:
            ya.append(it.nombre)
    db.session.commit()
    msg = "Traído del maestro: %s." % (", ".join(agregadas) if agregadas else "nada nuevo")
    if ya:
        msg += " Ya estaban incluidas: %s." % ", ".join(ya)
    return jsonify(ok=True, agregadas=agregadas, ya=ya, mensaje=msg)


@bp.route("/clientes/<int:cid>/asesorias-confirmar", methods=["POST"])
def cliente_asesorias_confirmar(cid):
    """Confirma el paquete de asesorias visible en la ficha:
    - fija la renta base del cliente (los % quedan amarrados a ella)
    - si el total difiere del presupuesto solo por redondeo (±$1.000), el
      presupuesto NO se toca; si difiere de verdad, se actualiza al valor real
    - registra log en el historial: primera vez con nota automatica 'Revision
      inicial', despues SIEMPRE con nota escrita por el usuario."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    nota = (request.form.get("motivo") or "").strip()
    filas, base = _asesorias_filas(cli, a)
    if not base or base <= 0:
        return jsonify(ok=False, error="No pude calcular la renta base (marca al menos una asesoría en % o revisa el presupuesto)")
    total = round(sum(f["subtotal"] for f in filas))
    p = PresupuestoCliente.query.filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first()
    if p is None:
        p = PresupuestoCliente(cliente_id=cid, anio_cobro=a.anio_cobro, valor=0.0)
        db.session.add(p)
    anterior = float(p.valor or 0)
    ya_historia = (db.session.query(PresupuestoHistorial.id)
                   .filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first() is not None)
    if not ya_historia and not nota:
        nota = "Revisión inicial"
    if not nota:
        return jsonify(ok=False, pide_nota=True,
                       error="Escribe la nota del cambio (es obligatoria desde la segunda confirmación)")
    cambios = []
    if anterior <= 0:
        cambios.append("aun no hay presupuesto construido: quedo amarrada la base y el paquete")
    elif total == anterior:
        cambios.append("paquete cuadra con el presupuesto")
    elif abs(total - anterior) <= 1000:
        cambios.append("diferencia de redondeo ($ %s) tolerada" % f"{total - anterior:,.0f}")
    else:
        return jsonify(ok=False, requiere_recalculo=True,
                       error="El paquete ($ %s) no cuadra con el presupuesto ($ %s). "
                             "Pulsa Recalcular (ajusta la base al presupuesto) y vuelve a guardar."
                       % (f"{total:,.0f}", f"{anterior:,.0f}"))
    cli.renta_base = base
    db.session.add(PresupuestoHistorial(cliente_id=cid, anio_cobro=a.anio_cobro,
                                        valor_anterior=anterior, valor_nuevo=float(anterior),
                                        motivo=nota[:300], fecha=date.today()))
    db.session.commit()
    msg = "Paquete confirmado. Renta base: $ %s. %s. Nota: %s" % (f"{base:,.0f}", ". ".join(cambios), nota[:80])
    return jsonify(ok=True, mensaje=msg, base=base, total=total, presupuesto=float(anterior))


@bp.route("/clientes/<int:cid>/presupuesto-paquete", methods=["POST"])
def cliente_presupuesto_paquete(cid):
    """Construye el presupuesto desde la BASE (modal de la ficha):
    aplica las marcas del modal, amarra la renta base y fija
    presupuesto = base x % marcados + tarifas fijas x cantidad.
    El valor NUNCA se digita: se calcula. Deja log obligatorio y
    regenera PDFs borrador / deja nota interna en ENVIADA-PAGADA."""
    import json as _json
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    try:
        base = float(request.form.get("base") or 0)
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Base inválida")
    if base <= 0:
        return jsonify(ok=False, error="La base debe ser mayor que cero")
    motivo = (request.form.get("motivo") or "").strip()
    ya_historia = (db.session.query(PresupuestoHistorial.id)
                   .filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first() is not None)
    if ya_historia and not motivo:
        return jsonify(ok=False, pide_nota=True,
                       error="Escribe el motivo del cambio (es obligatorio desde la segunda vez)")
    if not motivo:
        motivo = "Revisión inicial"
    try:
        marcas = _json.loads(request.form.get("marcas") or "[]")
    except (TypeError, ValueError):
        return jsonify(ok=False, error="Marcas inválidas")
    aplicar_marcas = (request.form.get("aplicar_marcas") or "1") == "1"
    items = {it.id: it for it in AsesoriaCatalogo.query.filter(AsesoriaCatalogo.activo == True).all()}
    aplicadas = 0
    for mrc in (marcas if aplicar_marcas else []):
        try:
            aid = int(mrc.get("id") or 0)
        except (TypeError, ValueError):
            continue
        it = items.get(aid)
        if not it:
            continue
        if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
            continue
        x = AsesoriaCliente.query.filter_by(cliente_id=cid, asesoria_id=it.id).first()
        if x is None:
            x = AsesoriaCliente(cliente_id=cid, asesoria_id=it.id)
            db.session.add(x)
        x.incluir = bool(mrc.get("incluir"))
        if it.es_fija:
            if mrc.get("valor") is not None:
                try:
                    v = float(mrc.get("valor") or 0)
                    x.valor = v if v > 0 else None
                except (TypeError, ValueError):
                    pass
            try:
                c = int(mrc.get("cantidad") or 1)
            except (TypeError, ValueError):
                c = 1
            x.cantidad = max(1, c)
        else:
            if mrc.get("pct") is not None:
                try:
                    q = float(mrc.get("pct") or 0)
                    x.pct = q if q > 0 else None
                except (TypeError, ValueError):
                    pass
        aplicadas += 1
    # total calculado con la MISMA fórmula de la ficha (sobre el estado recién aplicado)
    total = 0.0
    for it in items.values():
        if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
            continue
        x = AsesoriaCliente.query.filter_by(cliente_id=cid, asesoria_id=it.id).first()
        if x is None or not x.incluir:
            continue
        if it.es_fija:
            val = x.valor if (x.valor is not None and x.valor > 0) else float(it.defecto_valor or 0)
            total += val * (x.cantidad or 1)
        else:
            pct = x.pct if (x.pct is not None and x.pct > 0) else float(it.defecto_pct or 0)
            total += pct / 100.0 * base
    total = round(total)
    p = PresupuestoCliente.query.filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first()
    if p is None:
        p = PresupuestoCliente(cliente_id=cid, anio_cobro=a.anio_cobro, valor=0.0)
        db.session.add(p)
    anterior = float(p.valor or 0)
    p.valor = float(total)
    cli.renta_base = base
    db.session.add(PresupuestoHistorial(cliente_id=cid, anio_cobro=a.anio_cobro,
                                        valor_anterior=anterior, valor_nuevo=float(total),
                                        motivo=("base $ %s; %s" % (f"{base:,.0f}", motivo))[:300],
                                        fecha=date.today()))
    # cuentas BORRADOR: regenerar PDF; ENVIADA/PAGADA: nota interna (igual que antes)
    regenerados, marcadas = [], []
    lineas_cli = (CuentaLinea.query.filter_by(cliente_id=cid, estado="ACTIVA").all())
    cuentas = []
    for l in lineas_cli:
        cta = l.cuenta
        if cta.anio_cobro_id == a.id and cta.estado != "ANULADA" and cta not in cuentas:
            cuentas.append(cta)
    for cta in cuentas:
        if cta.estado == "BORRADOR" and cta.envios.count() == 0:
            carpeta = _carpeta_pdfs()
            generar_pdf(cta, os.path.join(carpeta, _nombre_pdf(cta)))
            regenerados.append(cta.numero_formateado)
        elif cta.estado in ("ENVIADA", "PAGADA") or cta.envios.count() > 0:
            nota = (f"Error en el cálculo de la cuenta. Valor real de servicios {a.anio_cobro}: "
                    f"$ {total:,.0f} (presupuesto anterior: $ {anterior:,.0f}). "
                    f"Motivo: {motivo[:200]}. Ver photo card en cliente.")
            cta.observaciones = ((cta.observaciones or "") + "\n" + nota).strip()
            marcadas.append(cta.numero_formateado)
    db.session.commit()
    msg = (f"Presupuesto {a.anio_cobro}: $ {anterior:,.0f} -> $ {total:,.0f} "
           f"(base $ {base:,.0f} × marcas). {aplicadas} asesorías aplicadas."
           + (f" PDF regenerado: {', '.join(regenerados)}." if regenerados else "")
           + (f" NOTA interna en: {', '.join(marcadas)}." if marcadas else ""))
    return jsonify(ok=True, base=base, total=total, presupuesto=float(total),
                   aplicadas=aplicadas, mensaje=msg)


@bp.route("/clientes/<int:cid>/asesorias-revertir", methods=["POST"])
def cliente_asesorias_revertir(cid):
    """Vuelve las marcas al estado que trae el maestro (borra las manuales).
    Repetible cuantas veces se quiera SIEMPRE que el paquete no haya sido
    confirmado (Guardar) en el año activo."""
    from flask import jsonify
    from .maestro import leer_maestro
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    ya = (db.session.query(PresupuestoHistorial.id)
          .filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first())
    if ya:
        return jsonify(ok=False, error="El paquete ya fue confirmado este año: "
                                       "no se puede revertir automáticamente")
    nit = (cli.nit or "").strip()
    if not nit:
        return jsonify(ok=False, error="El cliente no tiene NIT guardado")
    m = leer_maestro(a.anio_cobro, a.anio_gravable, {nit}) or {}
    bruto = m.get(nit) or {}
    cod2id = {c.codigo: c.id for c in AsesoriaCatalogo.query.all()}
    datos = {cod2id[k]: v for k, v in bruto.items() if k in cod2id}
    encendidas, apagadas = 0, 0
    items = AsesoriaCatalogo.query.filter(AsesoriaCatalogo.activo == True).all()
    for it in items:
        if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
            continue
        x = AsesoriaCliente.query.filter_by(cliente_id=cid, asesoria_id=it.id).first()
        debe = it.id in datos
        if x is None:
            if not debe:
                continue
            x = AsesoriaCliente(cliente_id=cid, asesoria_id=it.id, incluir=True)
            db.session.add(x)
            encendidas += 1
        else:
            if debe and not x.incluir:
                encendidas += 1
            if (not debe) and x.incluir:
                apagadas += 1
            x.incluir = debe
        # al revertir, los valores vuelven al estándar del catálogo
        x.pct = None
        x.valor = None
        if debe and it.es_fija:
            cant_m = datos[it.id][0] if datos[it.id][0] else 1
            x.cantidad = max(1, int(cant_m))
    db.session.commit()
    return jsonify(ok=True, encendidas=encendidas, apagadas=apagadas,
                   mensaje="Marcas revertidas al maestro: %d encendidas, %d apagadas."
                           % (encendidas, apagadas))


@bp.route("/clientes/asesorias-maestro-todos", methods=["POST"])
def clientes_asesorias_maestro_todos():
    """Trae del maestro lo PRESENTADO de TODOS los clientes activos (masivo)."""
    from .maestro import leer_maestro
    a = anio_actual()
    if not a:
        flash("No hay año activo", "error")
        return redirect(url_for("main.clientes"))
    activos = Cliente.query.filter_by(activo=True).all()
    nits = {(c.nit or "").strip() for c in activos} - {""}
    m = leer_maestro(a.anio_cobro, a.anio_gravable, nits) or {}
    cod2id = {c.codigo: c.id for c in AsesoriaCatalogo.query.all()}
    agregadas_total, sin_nit, sin_maestro = 0, [], []
    for cli in activos:
        nit = (cli.nit or "").strip()
        if not nit:
            sin_nit.append(cli.nombre)
            continue
        bruto = m.get(nit)
        if not bruto:
            sin_maestro.append(cli.nombre)
            continue
        datos = {cod2id[k]: v for k, v in bruto.items() if k in cod2id}
        for aid in datos:
            it = db.session.get(AsesoriaCatalogo, aid)
            if not it or not it.activo:
                continue
            if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
                continue
            x = AsesoriaCliente.query.filter_by(cliente_id=cli.id, asesoria_id=aid).first()
            if x is None:
                x = AsesoriaCliente(cliente_id=cli.id, asesoria_id=aid, incluir=True)
                if it.es_fija:
                    x.cantidad = max(1, datos[aid][0])
                db.session.add(x)
                agregadas_total += 1
            elif not x.incluir:
                x.incluir = True
                if it.es_fija:
                    x.cantidad = max(1, datos[aid][0])
                agregadas_total += 1
    db.session.commit()
    flash("Masivo: %d asesoría(s) marcada(s) del maestro. Sin datos en maestro: %d cliente(s). Sin NIT: %d."
          % (agregadas_total, len(sin_maestro), len(sin_nit)), "ok")
    return redirect(url_for("main.clientes"))



@bp.route("/clientes/<int:cid>/editar", methods=["GET", "POST"])
def cliente_editar(cid):
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if request.method == "POST":
        f = request.form
        cli.nombre = f["nombre"].strip().upper()
        cli.tipo = f.get("tipo", "PN")
        cli.trato = f.get("trato", "") if f.get("trato") in ("", "SR", "SRA") else ""
        cli.nit = f.get("nit", "").strip()
        cli.dv = f.get("dv", "").strip()
        cli.ciudad = f.get("ciudad", "").strip()
        cli.direccion = f.get("direccion", "").strip()
        cli.telefonos = f.get("telefonos", "").strip()
        cli.email = f.get("email", "").strip()
        cli.grupo_id = int(f["grupo_id"]) if f.get("grupo_id") else None
        cli.es_pagador = bool(f.get("es_pagador"))
        cli.nota = f.get("nota", "").strip()
        cli.activo = bool(f.get("activo"))
        valor = f.get("valor")
        if a and valor not in (None, ""):
            p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
            if p is None:
                p = PresupuestoCliente(cliente_id=cli.id, anio_cobro=a.anio_cobro)
                db.session.add(p)
            p.valor = float(valor or 0)
        if cli.es_pagador and cli.grupo_id:
            Cliente.query.filter(Cliente.grupo_id == cli.grupo_id,
                                 Cliente.id != cli.id).update({"es_pagador": False})
        db.session.commit()
        flash("Cliente actualizado", "ok")
        return redirect(url_for("main.cliente_detalle", cid=cli.id))
    presup_actual = None
    if a:
        presup_actual = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
    return render_template("cliente_form.html", cli=cli, a=a, presup_actual=presup_actual,
                           grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre))


# ---------------- Grupos familiares ----------------
def _pagos_miembros_anio():
    """Estado de pago individual (año activo) para la vista de grupos familiares.

    Devuelve {cliente_id: {"estado": "pagado"|"abono"|"pendiente", "pagado": x, "debe": y}}
    solo de quienes aparecen en alguna cuenta NO anulada del año. El dinero pagado a
    una cuenta se reparte proporcionalmente entre sus líneas (valor línea / total);
    los ajustes también se prorratean así. Cuenta PAGADA o saldo 0 => cada línea
    cubre su parte completa. Exceso de pago se limita a la parte del miembro."""
    a = AnioCobro.query.filter_by(activo=True).first()
    if not a:
        return {}
    acc = {}
    cuentas = (CuentaCobro.query.filter_by(anio_cobro_id=a.id)
               .filter(CuentaCobro.estado != "ANULADA").all())
    for cu in cuentas:
        lineas = [l for l in cu.lineas if l.estado == "ACTIVA"]
        tot = sum(float(l.valor or 0) for l in lineas)
        if tot <= 0:
            continue
        pagado = float(cu.total_pagado or 0)
        ajustes = float(cu.total_ajustes or 0)
        for l in lineas:
            fr = float(l.valor or 0) / tot
            parte = max(float(l.valor or 0) - ajustes * fr, 0.0)
            pag = min(pagado * fr, parte)
            d = acc.setdefault(l.cliente_id, {"pagado": 0.0, "debe": 0.0})
            d["debe"] += parte
            d["pagado"] += pag
    res = {}
    for cid, d in acc.items():
        debe, pag = d["debe"], d["pagado"]
        if pag >= debe - 0.5:
            est = "pagado"
        elif pag > 0.5:
            est = "abono"
        else:
            est = "pendiente"
        res[cid] = {"estado": est, "pagado": pag, "debe": debe}
    return res


@bp.route("/grupos")
def grupos():
    pagos = _pagos_miembros_anio()
    # estado por grupo para pintar la tarjeta: ok (todos pagaron) / parcial (abonos)
    estado_grupos = {}
    for g in GrupoFamiliar.query.all():
        ests = [pagos[c.id]["estado"] for c in g.miembros if c.id in pagos]
        if ests and all(e == "pagado" for e in ests):
            estado_grupos[g.id] = "ok"
        elif any(e == "abono" for e in ests):
            estado_grupos[g.id] = "parcial"
    return render_template("grupos.html",
                           pagos_map=pagos,
                           estado_grupos=estado_grupos,
                           grupos=GrupoFamiliar.query.order_by(GrupoFamiliar.nombre).all(),
                           clientes_sin_grupo=Cliente.query.filter_by(grupo_id=None, activo=True)
                           .order_by(Cliente.nombre).all())


@bp.route("/grupos/nuevo", methods=["POST"])
def grupo_nuevo():
    nombre = request.form.get("nombre", "").strip()
    if nombre:
        g = GrupoFamiliar(nombre=nombre.upper())
        db.session.add(g)
        db.session.commit()
        flash("Grupo creado", "ok")
    return redirect(url_for("main.grupos"))


@bp.route("/grupos/<int:gid>/renombrar", methods=["POST"])
def grupo_renombrar(gid):
    """Cambia el nombre visible del grupo (ej: G11 -> FAMILIA RESTREPO)."""
    g = db.session.get(GrupoFamiliar, gid)
    nombre = request.form.get("nombre", "").strip().upper()
    if g and nombre:
        viejo = g.nombre
        g.nombre = nombre
        db.session.commit()
        flash(f'Grupo "{viejo}" renombrado a "{nombre}"', "ok")
    return redirect(url_for("main.grupos"))


@bp.route("/grupos/<int:gid>/agregar", methods=["POST"])
def grupo_agregar(gid):
    data = request.get_json(silent=True) or {}
    cid = int(data.get("cliente_id") or request.form.get("cliente_id") or 0)
    cli = db.session.get(Cliente, cid)
    g = db.session.get(GrupoFamiliar, gid)
    if cli and g:
        cli.grupo_id = g.id
        if data.get("pagador") or request.form.get("pagador"):
            Cliente.query.filter(Cliente.grupo_id == g.id).update({"es_pagador": False})
            cli.es_pagador = True
        db.session.commit()
    return redirect(url_for("main.grupos"))


@bp.route("/grupos/<int:gid>/quitar/<int:cid>", methods=["POST"])
def grupo_quitar(gid, cid):
    cli = db.session.get(Cliente, cid)
    if cli:
        cli.grupo_id = None
        cli.es_pagador = False
        db.session.commit()
    return redirect(url_for("main.grupos"))


@bp.route("/grupos/<int:gid>/pagador/<int:cid>", methods=["POST"])
def grupo_pagador(gid, cid):
    Cliente.query.filter(Cliente.grupo_id == gid).update({"es_pagador": False})
    cli = db.session.get(Cliente, cid)
    if cli:
        cli.es_pagador = True
    db.session.commit()
    return redirect(url_for("main.grupos"))


@bp.route("/grupos/<int:gid>/eliminar", methods=["POST"])
def grupo_eliminar(gid):
    g = db.session.get(GrupoFamiliar, gid)
    if g:
        Cliente.query.filter_by(grupo_id=gid).update({"grupo_id": None, "es_pagador": False})
        db.session.delete(g)
        db.session.commit()
        flash("Grupo eliminado", "ok")
    return redirect(url_for("main.grupos"))


# ---------------- Cuentas de cobro ----------------
@bp.route("/cuentas")
def cuentas():
    a = anio_actual()
    if not a:
        return redirect(url_for("main.dashboard"))
    estado = request.args.get("estado", "")
    query = a.cuentas
    if estado:
        query = query.filter_by(estado=estado)
    return render_template("cuentas.html", a=a,
                           cuentas=query.order_by(CuentaCobro.numero).all(),
                           estado=estado, estados=ESTADOS)


def _cuenta_activa_de(cliente_id, anio_id):
    """Línea ACTIVA del cliente en una cuenta NO anulada del año (None si no existe).
    Se usa para impedir cuentas de cobro duplicadas."""
    return (CuentaLinea.query.join(CuentaCobro)
            .filter(CuentaLinea.cliente_id == cliente_id,
                    CuentaCobro.anio_cobro_id == anio_id,
                    CuentaLinea.estado == "ACTIVA",
                    CuentaCobro.estado != "ANULADA").first())


@bp.route("/cuentas/nueva", methods=["GET", "POST"])
def cuenta_nueva():
    a = anio_actual()
    if not a:
        return redirect(url_for("main.dashboard"))
    if request.method == "POST":
        f = request.form
        duplicados = []
        for cid_sel in request.form.getlist("clientes"):
            try:
                cli_sel = db.session.get(Cliente, int(cid_sel))
            except (TypeError, ValueError):
                continue
            if not cli_sel:
                continue
            ya_sel = _cuenta_activa_de(cli_sel.id, a.id)
            if ya_sel:
                duplicados.append(f"{cli_sel.nombre} (ya está en {ya_sel.cuenta.numero_formateado})")
        if duplicados:
            flash("Cuenta NO creada, quedaría duplicada. Estos clientes ya tienen cuenta este año: "
                  + ", ".join(duplicados), "error")
            return redirect(url_for("main.cuenta_nueva"))
        cuenta = CuentaCobro(anio_cobro_id=a.id, numero=_numero_libre(a),
                             fecha=date.today(), estado="BORRADOR")
        db.session.add(cuenta)
        db.session.flush()
        for cid in request.form.getlist("clientes"):
            cli = db.session.get(Cliente, int(cid))
            if not cli:
                continue
            val = f.get(f"valor_{cid}", "")
            if val == "":
                p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
                val = p.valor if p else 0
            con = (f.get(f"concepto_{cid}", "") or "").strip()
            db.session.add(CuentaLinea(cuenta=cuenta, cliente_id=cli.id, valor=float(val or 0),
                                       concepto=con))
        db.session.flush()
        pagador_id = int(f.get("pagador_id")) if f.get("pagador_id") else None
        if pagador_id and any(l.cliente_id == pagador_id for l in cuenta.lineas):
            cuenta.pagador_cliente_id = pagador_id
        cuenta.observaciones = (f.get("observaciones", "") or "").strip()
        a.numero_siguiente = cuenta.numero + 1
        db.session.commit()
        flash(f"Cuenta {cuenta.numero_formateado} creada en borrador", "ok")
        return redirect(url_for("main.cuenta_detalle", cid=cuenta.id))
    # GET: selector con presupuestos y grupos
    pares = []
    for p in PresupuestoCliente.query.filter_by(anio_cobro=a.anio_cobro).all():
        if p.cliente.activo:
            pares.append({"cliente": p.cliente, "valor": p.valor})
    pares.sort(key=lambda x: x["cliente"].nombre)
    grupos = GrupoFamiliar.query.order_by(GrupoFamiliar.nombre).all()
    pagadores = [p["cliente"] for p in pares]
    ya_en = {}
    for l in (CuentaLinea.query.join(CuentaCobro)
              .filter(CuentaLinea.estado == "ACTIVA",
                      CuentaCobro.anio_cobro_id == a.id,
                      CuentaCobro.estado != "ANULADA").all()):
        ya_en[l.cliente_id] = l.cuenta.numero_formateado
    return render_template("cuenta_nueva.html", a=a, pares=pares, grupos=grupos,
                           pagadores=pagadores, ya_en=ya_en)


@bp.route("/cuentas/<int:cid>")
def cuenta_detalle(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    ids_en_cuenta = {l.cliente_id for l in cuenta.lineas}
    todos = Cliente.query.filter_by(activo=True).order_by(Cliente.nombre).all()
    return render_template("cuenta_detalle.html", cuenta=cuenta,
                           todosClientes=[c for c in todos if c.id not in ids_en_cuenta],
                           todosPagadores=[l.cliente for l in cuenta.lineas],
                           formas=Pago.formas_pago())


@bp.route("/cuentas/<int:cid>/pdf")
def cuenta_pdf(cid):
    """Muestra el PDF inline (para pestaña nueva o modal), sin descargar."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    buf = io.BytesIO()
    from .pdf_generator import generar_desde_dict, _datos_cuenta
    generar_desde_dict(_datos_cuenta(cuenta), buf)
    buf.seek(0)
    return Response(buf, mimetype="application/pdf", headers={
        "Content-Disposition": f"inline; filename={_nombre_pdf(cuenta)}"})


@bp.route("/cuentas/preview", methods=["POST"])
def cuenta_preview():
    """PDF de previsualización SIN crear la cuenta ni gastar número.
    Recibe el mismo formulario de 'Nueva cuenta' por AJAX."""
    a = anio_actual()
    if not a:
        return ("Sin año activo", 400)
    f = request.form
    lineas = []
    pagador = None
    pid = int(f.get("pagador_id")) if f.get("pagador_id") else None
    for cid in request.form.getlist("clientes"):
        cli = db.session.get(Cliente, int(cid))
        if not cli:
            continue
        val = f.get(f"valor_{cid}", "")
        if val == "":
            p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
            val = p.valor if p else 0
        con = (f.get(f"concepto_{cid}", "") or "").strip()
        lineas.append({"nombre": cli.nombre, "concepto": con, "valor": float(val or 0)})
        if pid and cli.id == pid:
            pagador = cli
    if not lineas:
        return ("Selecciona al menos un cliente", 400)
    if pagador is None:
        ids_sel = [int(c) for c in request.form.getlist("clientes")]
        sel = [db.session.get(Cliente, i) for i in ids_sel]
        pagador = next((c for c in sel if c and c.es_pagador), None) or (sel[0] if sel else None)
    from .pdf_generator import generar_desde_dict, datos_preview
    d = datos_preview(a, lineas, pagador, obs=(f.get("observaciones", "") or "").strip())
    buf = io.BytesIO()
    generar_desde_dict(d, buf)
    buf.seek(0)
    return Response(buf, mimetype="application/pdf")


@bp.route("/cuentas/<int:cid>/linea/agregar", methods=["POST"])
def cuenta_linea_agregar(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    f = request.form
    cid_cli = int(f.get("cliente_id") or 0)
    if cid_cli:
        ya_ag = _cuenta_activa_de(cid_cli, cuenta.anio_cobro_id)
        if ya_ag:
            cli_ag = db.session.get(Cliente, cid_cli)
            flash(f"{cli_ag.nombre} ya está en la cuenta {ya_ag.cuenta.numero_formateado}: "
                  "no se agregó duplicado.", "error")
            return redirect(url_for("main.cuenta_detalle", cid=cid))
        val = f.get("valor", "")
        if val == "":
            a = cuenta.anio
            p = PresupuestoCliente.query.filter_by(cliente_id=cid_cli, anio_cobro=a.anio_cobro).first()
            val = p.valor if p else 0
        con = (f.get("concepto", "") or "").strip()
        db.session.add(CuentaLinea(cuenta_id=cuenta.id, cliente_id=cid_cli, valor=float(val or 0),
                                   concepto=con))
        db.session.commit()
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/lineas/<int:lid>/concepto", methods=["POST"])
def linea_concepto(lid):
    lin = db.get_or_404(CuentaLinea, lid)
    lin.concepto = (request.form.get("concepto", "") or "").strip()
    db.session.commit()
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/cuentas/<int:cid>/pagador", methods=["POST"])
def cuenta_pagador(cid):
    """Seleccionar a nombre de quién sale ESTA cuenta (sin cambiar el grupo)."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    pid = int(request.form.get("pagador_id") or 0)
    ids = {l.cliente_id for l in cuenta.lineas}
    cuenta.pagador_cliente_id = pid if pid in ids else None
    db.session.commit()
    flash("Pagador de la cuenta actualizado", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/lineas/<int:lid>/valor", methods=["POST"])
def linea_valor(lid):
    lin = db.get_or_404(CuentaLinea, lid)
    val = request.form.get("valor")
    if val not in (None, ""):
        lin.valor = float(val)
        db.session.commit()
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/lineas/<int:lid>/anular", methods=["POST"])
def linea_anular(lid):
    lin = db.get_or_404(CuentaLinea, lid)
    lin.estado = "ANULADA" if lin.estado == "ACTIVA" else "ACTIVA"
    lin.cuenta.marcar_estado()
    db.session.commit()
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/cuentas/<int:cid>/fecha", methods=["POST"])
def cuenta_fecha(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    f = request.form.get("fecha")
    if f:
        cuenta.fecha = date.fromisoformat(f)
        db.session.commit()
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/enviar", methods=["POST"])
def cuenta_enviar(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    f = request.form
    medio = f.get("medio", "Correo")
    fecha = f.get("fecha") or date.today().isoformat()
    db.session.add(Envio(cuenta_id=cuenta.id, medio=medio, fecha=date.fromisoformat(fecha),
                         nota=f.get("nota", "")))
    if cuenta.estado == "BORRADOR":
        cuenta.estado = "ENVIADA"
    db.session.commit()
    flash("Envío registrado", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/envio/<int:eid>/eliminar", methods=["POST"])
def envio_eliminar(cid, eid):
    """Deshacer un envío registrado por error (ej. descargar el .eml de un cliente
    al que todavía no se le ha hecho la declaración). Elimina el registro de envío
    y recalcula el estado: si era el único envío, la cuenta vuelve a BORRADOR."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    envio = db.session.get(Envio, eid)
    if envio is None or envio.cuenta_id != cuenta.id:
        flash("Ese envío no existe o no pertenece a esta cuenta.", "danger")
        return redirect(url_for("main.cuenta_detalle", cid=cid))
    info = f"{envio.medio} del {envio.fecha.strftime('%d/%m/%Y') if envio.fecha else '?'}"
    db.session.delete(envio)
    cuenta.marcar_estado()   # sin envíos y con saldo => BORRADOR (si pagó, sigue PAGADA)
    db.session.commit()
    flash(f"Envío eliminado ({info}). La cuenta volvió a BORRADOR: genera el correo de nuevo cuando toque.", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/pago", methods=["POST"])
def cuenta_pago(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    f = request.form
    valor = float(f.get("valor") or 0)
    if valor > 0:
        db.session.add(Pago(cuenta_id=cuenta.id, valor=valor,
                            fecha=date.fromisoformat(f.get("fecha") or date.today().isoformat()),
                            forma=f.get("forma", "Transferencia"),
                            nota=f.get("nota", "")))
    cuenta.marcar_estado()
    db.session.commit()
    flash("Pago registrado", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/ajuste", methods=["POST"])
def cuenta_ajuste(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    f = request.form
    valor = float(f.get("valor") or 0)
    if valor:
        db.session.add(Ajuste(cuenta_id=cuenta.id, valor=valor,
                              fecha=date.fromisoformat(f.get("fecha") or date.today().isoformat()),
                              motivo=f.get("motivo", "")))
        cuenta.marcar_estado()
        db.session.commit()
        flash("Ajuste registrado", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/ajustes/<int:aid>/editar", methods=["POST"])
def ajuste_editar(aid):
    """Edita valor/fecha/motivo de un ajuste ya registrado y regenera el PDF."""
    from .pdf_generator import generar_desde_dict, _datos_cuenta
    a = db.get_or_404(Ajuste, aid)
    cuenta = a.cuenta
    f = request.form
    try:
        a.valor = float(f.get("valor") or 0)
    except ValueError:
        a.valor = 0
    try:
        a.fecha = date.fromisoformat(f.get("fecha") or a.fecha.isoformat())
    except ValueError:
        pass
    a.motivo = (f.get("motivo") or "").strip()
    if cuenta.estado == "ANULADA":
        flash("La cuenta está ANULADA: no se puede editar el ajuste.", "error")
        return redirect(url_for("main.cuenta_detalle", cid=cuenta.id))
    cuenta.marcar_estado()
    db.session.commit()
    try:
        carpeta = _carpeta_pdfs()
        ruta = os.path.join(carpeta, _nombre_pdf(cuenta))
        generar_desde_dict(_datos_cuenta(cuenta), ruta)
    except Exception:
        pass
    flash("Ajuste actualizado y PDF regenerado.", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cuenta.id))


@bp.route("/ajustes/<int:aid>/eliminar", methods=["POST"])
def ajuste_eliminar(aid):
    """Elimina un ajuste (valor mal digitado) y regenera el PDF."""
    from .pdf_generator import generar_desde_dict, _datos_cuenta
    a = db.get_or_404(Ajuste, aid)
    cuenta = a.cuenta
    if cuenta.estado == "ANULADA":
        flash("La cuenta está ANULADA: no se puede eliminar el ajuste.", "error")
        return redirect(url_for("main.cuenta_detalle", cid=cuenta.id))
    db.session.delete(a)
    cuenta.marcar_estado()
    db.session.commit()
    try:
        carpeta = _carpeta_pdfs()
        ruta = os.path.join(carpeta, _nombre_pdf(cuenta))
        generar_desde_dict(_datos_cuenta(cuenta), ruta)
    except Exception:
        pass
    flash("Ajuste eliminado y PDF regenerado.", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cuenta.id))


@bp.route("/cuentas/<int:cid>/anular", methods=["POST"])
def cuenta_anular(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    motivo = (request.form.get("motivo") or "").strip()
    if not motivo:
        flash("El motivo de la anulación es obligatorio.", "error")
        return redirect(url_for("main.cuenta_detalle", cid=cid))
    cuenta.estado = "ANULADA"   # el número queda conservado, no se reutiliza
    cuenta.motivo_anulacion = motivo
    db.session.commit()
    flash(f"Cuenta {cuenta.numero_formateado} ANULADA. Motivo: {motivo}. El número no se reutiliza.", "ok")
    return redirect(url_for("main.cuentas"))


@bp.route("/cuentas/<int:cid>/eliminar", methods=["POST"])
def cuenta_eliminar(cid):
    """Elimina una cuenta SIN envíos registrados y libera el número si era el último."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    if cuenta.envios.count() > 0:
        flash("Esta cuenta ya tiene envíos registrados: no se puede eliminar, solo ANULAR con motivo.", "error")
        return redirect(url_for("main.cuenta_detalle", cid=cid))
    a = cuenta.anio
    numero = cuenta.numero_formateado
    if a.numero_siguiente > cuenta.numero:
        a.numero_siguiente = cuenta.numero   # libera el consecutivo
    db.session.delete(cuenta)
    db.session.commit()
    flash(f"Cuenta {numero} eliminada. El número {numero} queda disponible de nuevo.", "ok")
    return redirect(url_for("main.cuentas"))


@bp.route("/cuentas/<int:cid>/sincronizar-grupo", methods=["POST"])
def cuenta_sincronizar_grupo(cid):
    """Agrega a la cuenta los miembros ACTIVOS del grupo del pagador que falten
    (con su presupuesto del año) y regenera el PDF. Si la cuenta ya tiene envíos,
    regenera también el borrador .eml de Outlook y lo registra."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    destino = url_for("main.cuenta_detalle", cid=cid)
    if cuenta.estado == "ANULADA":
        flash("Cuenta anulada: no se puede sincronizar.", "error")
        return redirect(destino)
    a = cuenta.anio
    pagador = cuenta.pagador_principal
    if not pagador or not pagador.grupo_id:
        flash("Esta cuenta no es de un grupo familiar (el pagador no tiene grupo).", "error")
        return redirect(destino)
    g = pagador.grupo
    agregados, problemas = [], []
    for m in g.miembros:
        if not m.activo:
            continue
        if any(l.cliente_id == m.id and l.estado == "ACTIVA" for l in cuenta.lineas):
            continue
        ya = _cuenta_activa_de(m.id, a.id)
        if ya:
            problemas.append(f"{m.nombre} (ya está en {ya.cuenta.numero_formateado})")
            continue
        p = PresupuestoCliente.query.filter_by(cliente_id=m.id, anio_cobro=a.anio_cobro).first()
        if not p or p.valor <= 0:
            problemas.append(f"{m.nombre} (sin presupuesto {a.anio_cobro})")
            continue
        db.session.add(CuentaLinea(cuenta=cuenta, cliente_id=m.id, valor=p.valor))
        agregados.append(m.nombre)
    if not agregados:
        msg = "Nada que sincronizar: la cuenta ya tiene a todos los miembros activos del grupo."
        if problemas:
            msg += " Faltaban, pero: " + ", ".join(problemas)
        flash(msg, "error")
        return redirect(destino)
    db.session.commit()
    carpeta = _carpeta_pdfs()
    ruta = os.path.join(carpeta, _nombre_pdf(cuenta))
    generar_pdf(cuenta, ruta)
    msg = (f"Sincronizado: se agregaron {len(agregados)} miembro(s) del grupo {g.nombre}: "
           + ", ".join(agregados) + f". Nuevo total $ {cuenta.total:,.0f}. PDF regenerado en {ruta}")
    if problemas:
        msg += ". Ojo: " + ", ".join(problemas)
    hubo_envios = cuenta.envios.count() > 0
    pag = cuenta.pagador_principal
    if hubo_envios and pag and (pag.email or "").strip():
        ccorreos = _carpeta_correos()
        if _generar_eml(cuenta, ccorreos):
            db.session.add(Envio(cuenta_id=cuenta.id, medio="Correo", fecha=date.today(),
                                 nota=f"Borrador .eml regenerado con el grupo completo en {ccorreos} "
                                      f"(para {pag.email})"))
            if cuenta.estado == "BORRADOR":
                cuenta.estado = "ENVIADA"
            db.session.commit()
            msg += f". Borrador de Outlook (.eml) regenerado en {ccorreos}"
    elif not hubo_envios:
        msg += ". La cuenta sigue en BORRADOR: usa 'Redactar correo' cuando quieras y saldrá con el grupo completo."
    flash(msg, "ok")
    return redirect(destino)


def _generar_eml(cuenta, carpeta, extra=""):
    """Genera el PDF de la cuenta (en `carpeta`) y su .eml de borrador de Outlook
    (X-Unsent) con destinatario, asunto, cuerpo de la oficina y PDF adjunto.
    Requiere pagador con correo. Devuelve la ruta del .eml."""
    from email.message import EmailMessage
    from email.utils import formatdate, make_msgid

    pagador = cuenta.pagador_principal
    if not pagador or not (pagador.email or "").strip():
        return None
    ruta_pdf = os.path.join(carpeta, _nombre_pdf(cuenta))
    generar_pdf(cuenta, ruta_pdf)
    asunto = f"Declaración y Cuenta de cobro asesoría tributaria AG {cuenta.anio.anio_gravable}"
    if pagador.grupo:
        gn = (pagador.grupo.nombre or "").strip()
        if re.fullmatch(r"(?i)G\d+", gn):        # G22 -> apellido del pagador
            apellidos = " ".join((pagador.nombre or "").split()[:2])
            asunto += f" - Familia {apellidos.title()}"
        else:
            asunto += f" - {gn.title()}"
    else:
        asunto += f" - {pagador.nombre.title()}"
    cuerpo = _cuerpo_correo(cuenta, pagador, extra=extra)
    eml = EmailMessage()
    eml["X-Unsent"] = "1"
    remitente = Parametro.get("emisor_email", "").strip()
    if remitente:
        eml["From"] = remitente
    eml["To"] = (pagador.email or "").strip()
    eml["Subject"] = asunto
    eml["Date"] = formatdate(localtime=True)
    eml["Message-ID"] = make_msgid()
    eml.set_content(cuerpo, cte="8bit")   # UTF-8 plano: sin =C3=.. ni cortes de línea tipo "can=celación"
    with open(ruta_pdf, "rb") as fh:
        eml.add_attachment(fh.read(), maintype="application", subtype="pdf",
                           filename=os.path.basename(ruta_pdf))
    ruta_eml = os.path.join(carpeta, os.path.splitext(os.path.basename(ruta_pdf))[0] + ".eml")
    with open(ruta_eml, "wb") as fh:
        fh.write(bytes(eml))
    return ruta_eml


@bp.route("/cuentas/<int:cid>/outlook", methods=["POST"])
def cuenta_outlook(cid):
    """Genera el PDF y un archivo .eml (borrador de correo estándar) en la carpeta
    configurada. Al abrir el .eml (doble clic) se monta como borrador editable en
    Outlook (o el cliente de correo asociado) con destinatario, asunto, cuerpo y PDF
    adjunto, listo para revisar y enviar. Sin COM ni hilos: cero errores de permisos."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    pagador = cuenta.pagador_principal
    if not pagador or not (pagador.email or "").strip():
        flash(f"El pagador {pagador.nombre if pagador else '(sin pagador)'} no tiene correo guardado.", "error")
        return redirect(url_for("main.cuenta_detalle", cid=cid))
    carpeta = _carpeta_correos()
    _generar_eml(cuenta, carpeta, extra=request.form.get("correo_extra", ""))

    db.session.add(Envio(cuenta_id=cuenta.id, medio="Correo", fecha=date.today(),
                         nota=f"Borrador .eml generado en {carpeta} (para {pagador.email})"))
    if cuenta.estado == "BORRADOR":
        cuenta.estado = "ENVIADA"
    db.session.commit()
    flash(f"PDF y borrador de correo (.eml) guardados en {carpeta}. "
          "Abre el .eml (doble clic), revisa y envía.", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/reactivar", methods=["POST"])
def cuenta_reactivar(cid):
    cuenta = db.get_or_404(CuentaCobro, cid)
    cuenta.marcar_estado()
    if cuenta.estado == "ANULADA":
        cuenta.estado = "ENVIADA" if cuenta.envios.count() else "BORRADOR"
    db.session.commit()
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/nota", methods=["POST"])
def cuenta_nota(cid):
    """Guarda nota interna y/o observaciones del PDF. La nota interna JAMÁS sale en el PDF."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    cuenta.nota = request.form.get("nota", "")
    cuenta.observaciones = request.form.get("observaciones", "")
    db.session.commit()
    flash("Notas guardadas", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/descargar", methods=["POST"])
def cuenta_descargar(cid):
    """Descarga rápida: guarda el PDF directamente en la carpeta configurada en
    Parámetros (sin preguntar nada) y avisa la ruta exacta."""
    cuenta = db.get_or_404(CuentaCobro, cid)
    carpeta = _carpeta_pdfs()
    ruta = os.path.join(carpeta, _nombre_pdf(cuenta))
    generar_pdf(cuenta, ruta)
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, ruta=ruta)
    flash(f"PDF guardado en: {ruta}", "ok")
    return redirect(url_for("main.cuenta_detalle", cid=cid))


@bp.route("/cuentas/<int:cid>/imagen", methods=["POST"])
def cuenta_imagen(cid):
    """Genera imagen PNG de la cuenta (para WhatsApp) en la carpeta de imágenes
    configurada en Parámetros (vacía = carpeta de PDFs) y la descarga también
    al navegador. El PNG NO reemplaza el PDF: es una lámina para compartir."""
    from .imagen_cuenta import generar_imagen, _nombre_imagen
    cuenta = db.get_or_404(CuentaCobro, cid)
    carpeta = _carpeta_imagenes()
    ruta = os.path.join(carpeta, _nombre_imagen(cuenta))
    generar_imagen(cuenta, ruta)
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True, ruta=ruta)
    flash(f"Imagen guardada en: {ruta}", "ok")
    return redirect(request.referrer or url_for("main.cuentas"))


# ---------------- Tareas (notas rapidas por cliente) ----------------
@bp.app_context_processor
def _tareas_pendientes_global():
    """Conteo global de tareas pendientes para el badge del menu."""
    try:
        n = Tarea.query.filter_by(hecha=False).count()
    except Exception:
        n = 0
    return {"tareas_pend_count": n}


@bp.route("/tareas")
def tareas():
    """Modulo Tareas: pendientes (y hechas en historial) de todos los clientes."""
    ver = request.args.get("ver", "pendientes")
    q = Tarea.query.join(Cliente).filter(Cliente.activo == True)  # noqa: E712
    if ver == "hechas":
        q = q.filter(Tarea.hecha == True)   # noqa: E712
    else:
        ver = "pendientes"
        q = q.filter(Tarea.hecha == False)  # noqa: E712
    lista_t = q.order_by(Tarea.fecha.desc(), Tarea.id.desc()).all()
    return render_template("tareas.html", ver=ver, tareas=lista_t)


@bp.route("/clientes/<int:cid>/tareas")
def cliente_tareas(cid):
    """Tareas de un cliente (para el modal del listado)."""
    cli = db.get_or_404(Cliente, cid)
    ts = Tarea.query.filter_by(cliente_id=cid).order_by(Tarea.hecha, Tarea.fecha.desc(), Tarea.id.desc()).all()
    if request.accept_mimetypes.best == "application/json":
        return jsonify(ok=True,
                       pend=[{"id": t.id, "texto": t.texto, "fecha": t.fecha.isoformat()} for t in ts if not t.hecha],
                       hechas=[{"id": t.id, "texto": t.texto, "fecha": t.fecha.isoformat()} for t in ts if t.hecha])
    return render_template("_tareas_cliente.html", cli=cli, tareas=ts)


@bp.route("/clientes/<int:cid>/tarea-nueva", methods=["POST"])
def cliente_tarea_nueva(cid):
    """Crea una nota rapida para el cliente."""
    cli = db.get_or_404(Cliente, cid)
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        if request.accept_mimetypes.best == "application/json":
            return jsonify(ok=False, error="La nota esta vacia")
        flash("La nota esta vacia", "error")
        return redirect(request.referrer or url_for("main.clientes"))
    t = Tarea(cliente_id=cid, texto=texto[:500])
    db.session.add(t)
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        n = Tarea.query.filter_by(cliente_id=cid, hecha=False).count()
        return jsonify(ok=True, id=t.id, pendientes=n,
                       mensaje=f"tarea guardada ({n} pendiente{'s' if n != 1 else ''} para {cli.nombre})")
    flash(f"Tarea guardada para {cli.nombre}", "ok")
    return redirect(request.referrer or url_for("main.clientes"))


@bp.route("/tareas/<int:tid>/estado", methods=["POST"])
def cliente_tarea_estado(tid):
    """Marca/desmarca hecha una tarea. JSON o redirect segun origen."""
    t = db.get_or_404(Tarea, tid)
    t.hecha = not t.hecha
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        n = Tarea.query.filter_by(cliente_id=t.cliente_id, hecha=False).count()
        return jsonify(ok=True, hecha=t.hecha, pendientes=n,
                       mensaje=("marcada HECHA: " if t.hecha else "volvio a PENDIENTE: ") + t.texto[:80])
    flash(("Tarea marcada hecha: " if t.hecha else "Tarea devuelta a pendiente: ") + t.texto[:80], "ok")
    return redirect(request.referrer or url_for("main.tareas"))


@bp.route("/tareas/<int:tid>/borrar", methods=["POST"])
def cliente_tarea_borrar(tid):
    """Borra definitivamente una tarea (del historial)."""
    t = db.get_or_404(Tarea, tid)
    cid = t.cliente_id
    txt = t.texto[:80]
    db.session.delete(t)
    db.session.commit()
    if request.accept_mimetypes.best == "application/json":
        n = Tarea.query.filter_by(cliente_id=cid, hecha=False).count()
        return jsonify(ok=True, pendientes=n, mensaje=f"tarea borrada: {txt}")
    flash(f"Tarea borrada: {txt}", "ok")
    return redirect(request.referrer or url_for("main.tareas"))


# ---------------- Exportar a Excel ----------------
@bp.route("/exportar/excel")
def exportar_excel():
    """Libro con 5 hojas: Resumen, Cuentas, Pagos, Clientes y Maestro."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    a = anio_actual()
    wb = Workbook()
    morado = "FF6D28D9"
    h1 = Font(bold=True, color="FFFFFFFF")
    fill = PatternFill("solid", fgColor=morado)

    def _hoja(ws, cabeceras, filas, anchos):
        ws.append(cabeceras)
        for c, wdt in enumerate(anchos, 1):
            ws.column_dimensions[get_column_letter(c)].width = wdt
            ws.cell(row=1, column=c).font = h1
            ws.cell(row=1, column=c).fill = fill
        for fila in filas:
            ws.append(list(fila))
        ws.freeze_panes = "A2"

    # Hoja 1: Resumen
    ws = wb.active
    ws.title = "Resumen"
    if a:
        presup = db.session.query(db.func.coalesce(db.func.sum(PresupuestoCliente.valor), 0.0))\
            .filter_by(anio_cobro=a.anio_cobro).scalar()
        emitido = db.session.query(db.func.coalesce(db.func.sum(CuentaLinea.valor), 0.0))\
            .join(CuentaCobro).filter(CuentaCobro.anio_cobro_id == a.id,
                                      CuentaLinea.estado == "ACTIVA",
                                      CuentaCobro.estado != "ANULADA").scalar()
        pagado = db.session.query(db.func.coalesce(db.func.sum(Pago.valor), 0.0))\
            .join(CuentaCobro).filter(CuentaCobro.anio_cobro_id == a.id,
                                      CuentaCobro.estado != "ANULADA").scalar()
        ajustes = db.session.query(db.func.coalesce(db.func.sum(Ajuste.valor), 0.0))\
            .join(CuentaCobro).filter(CuentaCobro.anio_cobro_id == a.id,
                                      CuentaCobro.estado != "ANULADA").scalar()
        filas = [("Año de cobro", a.anio_cobro), ("Año gravable", a.anio_gravable),
                 ("Presupuestado", presup), ("Emitido en cuentas", emitido),
                 ("Pagado", pagado), ("Ajustes/descuentos", ajustes),
                 ("Saldo por cobrar", emitido - ajustes - pagado),
                 ("Próximo número", f"{a.prefijo}-{a.numero_siguiente:03d}")]
    else:
        filas = [("Sin año activo", "")]
    _hoja(ws, ["Concepto", "Valor"], filas, [26, 22])

    # Hoja 2: Cuentas (una fila por cliente/línea)
    ws = wb.create_sheet("Cuentas")
    filas = []
    q = CuentaCobro.query.filter(CuentaCobro.estado != "ANULADA")
    if a:
        q = q.filter_by(anio_cobro_id=a.id)
    for c in q.order_by(CuentaCobro.numero):
        for l in c.lineas:
            if l.estado != "ACTIVA":
                continue
            filas.append((c.numero_formateado, c.fecha, c.estado, l.cliente.codigo,
                          l.cliente.nombre, l.valor, c.total_ajustes, c.total_pagado,
                          c.saldo, (c.pagador_principal.nombre if c.pagador_principal else ""),
                          c.motivo_anulacion or ""))
    _hoja(ws, ["Cuenta", "Fecha", "Estado", "Código", "Cliente", "Valor línea",
               "Ajustes cuenta", "Pagado cuenta", "Saldo cuenta", "Pagador", "Motivo anulación"],
          filas, [10, 12, 10, 8, 38, 13, 13, 13, 13, 38, 28])

    # Hoja 3: Pagos (un registro por pago/abono)
    ws = wb.create_sheet("Pagos")
    filas = []
    q = Pago.query.join(CuentaCobro).filter(CuentaCobro.estado != "ANULADA")
    if a:
        q = q.filter(CuentaCobro.anio_cobro_id == a.id)
    for p in q.order_by(Pago.fecha):
        filas.append((p.cuenta.numero_formateado, p.fecha,
                      " / ".join(l.cliente.nombre for l in p.cuenta.lineas if l.estado == "ACTIVA"),
                      p.valor, p.forma, p.nota or ""))
    _hoja(ws, ["Cuenta", "Fecha", "Clientes", "Valor", "Forma", "Nota"],
          filas, [10, 12, 45, 13, 16, 30])

    # Hoja 4: Clientes con presupuesto y presupuesto del año
    ws = wb.create_sheet("Clientes")
    filas = []
    presup = {}
    if a:
        for p in PresupuestoCliente.query.filter_by(anio_cobro=a.anio_cobro):
            presup[p.cliente_id] = p
    for cli in Cliente.query.order_by(Cliente.nombre):
        p = presup.get(cli.id)
        filas.append((cli.codigo, cli.nombre, cli.tipo, cli.nit, cli.dv, cli.ciudad,
                      cli.telefonos or "", cli.email or "",
                      cli.grupo.nombre if cli.grupo else "", "Sí" if cli.es_pagador else "",
                      p.valor if p else 0, "Sí" if cli.activo else "No", cli.nota or ""))
    _hoja(ws, ["Código", "Nombre", "Tipo", "CC/NIT", "DV", "Ciudad", "Teléfonos",
               "Email", "Grupo", "Pagador", "Presupuesto", "Activo", "Nota"],
          filas, [8, 38, 6, 14, 5, 12, 14, 28, 22, 9, 13, 8, 30])

    # Hoja 5: Maestro (espejo del Excel clásico: TODOS los clientes activos con su
    # presupuesto del año, y el estado de cobro se va llenando a medida que hay cuentas)
    ws = wb.create_sheet("Maestro")
    filas = []
    # mapa cliente -> línea ACTIVA más reciente del año (para cuentas y pagos por cliente)
    por_cliente = {}
    q = CuentaCobro.query.filter(CuentaCobro.estado != "ANULADA")
    if a:
        q = q.filter_by(anio_cobro_id=a.id)
    for c in q.order_by(CuentaCobro.numero):
        for l in c.lineas:
            if l.estado != "ACTIVA":
                continue
            por_cliente[l.cliente_id] = (c, l)
    for cli in Cliente.query.filter_by(activo=True).order_by(Cliente.nombre):
        pres = presup.get(cli.id)
        cta = por_cliente.get(cli.id)
        if not cta:
            # sin cuenta todavía: presupuesto visible, cobro en blanco
            filas.append((len(filas) + 1, cli.nombre, cli.codigo, cli.nit_formateado, cli.dv,
                          float(pres.valor or 0) if pres else 0.0,
                          "", "", "", "", "", "", "", None, None))
            continue
        c, l = cta
        ue = c.ultimo_envio
        pagos_cta = sorted(c.pagos.all(), key=lambda p: p.fecha)
        pagado_cta = sum(p.valor for p in pagos_cta)
        saldo_cta = c.saldo
        if c.estado == "ANULADA":
            estado_cobro = "ANULADA"
        elif saldo_cta <= 0 and c.total > 0:
            estado_cobro = "PAGADO"
        elif c.estado == "ENVIADA" or c.envios.count() > 0:
            estado_cobro = "ENVIADA"
        else:
            estado_cobro = "PENDIENTE"
        medio = ue.medio if ue else (pagos_cta[-1].forma if pagos_cta and c.estado != "BORRADOR" else "")
        filas.append((len(filas) + 1, cli.nombre, cli.codigo, cli.nit_formateado, cli.dv,
                      float(l.valor or 0), c.numero_formateado,
                      "Sí" if (ue or c.estado in ("ENVIADA", "PAGADA")) else "",
                      ue.fecha.strftime("%d/%m/%Y") if ue else "",
                      estado_cobro,
                      medio,
                      pagos_cta[-1].fecha.strftime("%d/%m/%Y") if pagos_cta else "",
                      (c.observaciones or "")[:80],
                      pagado_cta if pagado_cta else None,
                      saldo_cta if saldo_cta and saldo_cta > 0 else None))
    _hoja(ws, ["No.", "APELLIDOS Y NOMBRES / RAZÓN SOCIAL", "CÓDIGO", "NIT No.", "D.V.",
               "VALOR CUENTA DE COBRO", "CUENTA DE COBRO No.", "ENVIADA", "FECHA ENVÍO",
               "ESTADO DEL COBRO", "MEDIO DE PAGO", "FECHA DE PAGO", "OBSERVACIONES",
               "PAGADO", "SALDO"],
          filas, [6, 42, 9, 15, 5, 16, 12, 9, 12, 15, 16, 12, 30, 12, 12])
    # Hoja 6: Morosos y acuerdos del año anterior (con la nota de cada cierre)
    ws = wb.create_sheet("Morosos y acuerdos")
    anio_ant = (a.anio_cobro - 1) if a else ""
    mor_mor, mor_acu = [], []
    for cli in Cliente.query.filter_by(activo=True).order_by(Cliente.nombre):
        pa = float(cli.cobrado_anterior or 0)
        ef = float(cli.cobrado_anterior_real or 0)
        if pa <= 0 or ef >= pa - 0.5:
            continue
        dif = pa - ef
        dato = ("ACUERDO INTERNO" if cli.moroso_cerrado else "MOROSO",
                cli.codigo, cli.nombre, pa, ef, dif, (cli.moroso_nota or ""))
        (mor_acu if cli.moroso_cerrado else mor_mor).append(dato)
    filas = mor_mor + mor_acu
    filas.append(("", "", "TOTAL MOROSOS (por cobrar)", "", "",
                  sum(x[5] for x in mor_mor), ""))
    filas.append(("", "", "TOTAL DESCONTADO (acuerdos internos)", "", "",
                  sum(x[5] for x in mor_acu), ""))
    _hoja(ws, ["Estado", "Código", "Cliente", f"Cobrado {anio_ant}",
               f"Efect. pagado {anio_ant}", "Falta / descontado",
               "Nota (acuerdo interno, descuento...)"],
          filas, [18, 8, 38, 14, 14, 15, 55])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"Cobros_{a.prefijo if a else 'general'}_{date.today().isoformat()}.xlsx"
    return Response(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


# ---------------- Plantilla + importador de clientes ----------------
@bp.route("/clientes/plantilla")
def clientes_plantilla():
    """Descarga la plantilla para importar/actualizar clientes."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "Clientes"
    cabeceras = ["Código", "Nombre", "Tipo", "CC/NIT", "DV", "Ciudad", "Dirección",
                 "Teléfonos", "Email", "Grupo", "Pagador", "Activo", "Nota",
                 "Presupuesto", "C de C año anterior"]
    anchos = [8, 38, 7, 14, 5, 12, 26, 14, 28, 10, 9, 8, 30, 13, 18]
    h1 = Font(bold=True, color="FFFFFFFF")
    fill = PatternFill("solid", fgColor="FF6D28D9")
    ws.append(cabeceras)
    for c, wdt in enumerate(anchos, 1):
        ws.column_dimensions[get_column_letter(c)].width = wdt
        ws.cell(row=1, column=c).font = h1
        ws.cell(row=1, column=c).fill = fill
    ejemplo = [41, "PÉREZ GÓMEZ JUAN", "PN", "123456789", "", "MEDELLÍN",
               "CR 00 00-00", "3000000000", "juan@correo.com", "", "NO", "Sí", "NO DECLARANTE",
               470000, 430000]
    ws.append(ejemplo)
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return Response(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": "attachment; filename=plantilla_clientes.xlsx"})


@bp.route("/clientes/importar", methods=["POST"])
def clientes_importar():
    """Importa/actualiza clientes desde la plantilla. Código es la llave.
    Las columnas se detectan por su CABECERA (acepta la plantilla del sistema y el
    Clientes.xlsx de Felipe; las columnas desconocidas se ignoran)."""
    f = request.files.get("archivo")
    if not f or not f.filename:
        flash("Selecciona el archivo Excel", "error")
        return redirect(url_for("main.clientes"))
    import openpyxl
    crear_nuevos = (request.form.get("cliente_nuevo") or "").strip().upper() == "SI"

    def _norm_hdr(s):
        import unicodedata as _u
        s = _u.normalize("NFD", str(s or ""))
        s = "".join(ch for ch in s if _u.category(ch) != "Mn").upper().strip()
        return s

    ALIAS = {
        "CODIGO": "codigo", "NOMBRE": "nombre", "TIPO": "tipo", "NIT": "nit",
        "CC/NIT": "nit", "DV": "dv", "CIUDAD": "ciudad", "DIRECCION": "direccion",
        "TELEFONOS": "telefonos", "TELEFONO": "telefonos", "EMAIL": "email", "CORREO": "email",
        "GRUPO": "grupo",
        "PAGADOR": "pagador", "ES_PAGADOR": "pagador",
        "ACTIVO": "activo", "NOTA": "nota", "PRESUPUESTO": "presupuesto",
        "C DE C ANO ANTERIOR": "cobrado_anterior", "COBRADO ANO ANTERIOR": "cobrado_anterior",
    }
    try:
        wb = openpyxl.load_workbook(f, data_only=True)
        ws = wb["Clientes"] if "Clientes" in wb.sheetnames else wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            flash("El archivo está vacío", "error")
            return redirect(url_for("main.clientes"))
        # mapa cabecera -> índice de columna
        idx = {}
        for j, h in enumerate(rows[0]):
            key = ALIAS.get(_norm_hdr(h))
            if key and key not in idx:
                idx[key] = j
        if "codigo" not in idx or "nombre" not in idx:
            flash("No encontré las columnas 'Código' y 'Nombre' en la primera fila", "error")
            return redirect(url_for("main.clientes"))
        grupos = {g.nombre.upper(): g for g in GrupoFamiliar.query.all()}
        a = anio_actual()
        stats = {"creados": 0, "actualizados": 0, "presupuestos": 0, "errores": []}
        for i, row in enumerate(rows[1:], start=2):
            val = lambda k: (row[idx[k]] if k in idx and idx[k] < len(row) and row[idx[k]] is not None else "")
            sv = lambda k: str(val(k)).strip()
            codigo = row[idx["codigo"]]
            nombre = sv("nombre")
            if codigo in (None, "") or not nombre:
                continue  # fila vacía
            try:
                codigo = int(float(codigo))
            except (TypeError, ValueError):
                stats["errores"].append(f"Fila {i}: código inválido")
                continue
            tipo = sv("tipo").upper() or "PN"
            tipo = "PJ" if tipo.startswith("PJ") else "PN"
            activo = sv("activo").upper() != "NO"
            cli = Cliente.query.filter_by(codigo=codigo).first()
            if cli is None:
                if not crear_nuevos:
                    stats["errores"].append(f"Fila {i}: cliente {codigo} no existe (y no se permiten nuevos)")
                    continue
                cli = Cliente(codigo=codigo, activo=activo)
                db.session.add(cli)
                stats["creados"] += 1
            else:
                stats["actualizados"] += 1
            cli.nombre = nombre.upper()
            cli.tipo = tipo
            cli.nit = sv("nit")
            cli.dv = sv("dv")
            cli.ciudad = sv("ciudad") or "MEDELLÍN"
            if "direccion" in idx:
                cli.direccion = sv("direccion")
            if "telefonos" in idx:
                cli.telefonos = sv("telefonos")
            if "email" in idx:
                cli.email = sv("email")
            if "nota" in idx:
                cli.nota = sv("nota")
            if "cobrado_anterior" in idx and val("cobrado_anterior") not in ("",):
                try:
                    cli.cobrado_anterior = float(val("cobrado_anterior"))
                except (TypeError, ValueError):
                    stats["errores"].append(f"Fila {i}: 'C de C año anterior' inválido")
            # grupo y pagador
            gn = sv("grupo").upper()
            if gn and gn != "NO":
                g = grupos.get(gn)
                if g is None:
                    g = GrupoFamiliar(nombre=gn)
                    db.session.add(g)
                    db.session.flush()
                    grupos[gn] = g
                cli.grupo_id = g.id
            elif gn == "NO" or (not gn and "grupo" in idx):
                cli.grupo_id = None
                cli.es_pagador = False
            pagador_txt = sv("pagador").upper()
            if pagador_txt == "SI" and cli.grupo_id:
                Cliente.query.filter(Cliente.grupo_id == cli.grupo_id,
                                     Cliente.id != cli.id).update({"es_pagador": False})
                cli.es_pagador = True
            elif pagador_txt == "NO" and cli.grupo_id:
                cli.es_pagador = False
            # presupuesto del año activo (si la columna existe)
            if a and "presupuesto" in idx and val("presupuesto") not in ("",):
                try:
                    v = float(val("presupuesto"))
                    p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
                    if p is None:
                        p = PresupuestoCliente(cliente_id=cli.id, anio_cobro=a.anio_cobro, valor=v)
                        db.session.add(p)
                    else:
                        p.valor = v
                    stats["presupuestos"] += 1
                except (TypeError, ValueError):
                    stats["errores"].append(f"Fila {i}: presupuesto inválido")
        db.session.commit()
        msg = f"Importación lista: {stats['creados']} creados, {stats['actualizados']} actualizados, {stats['presupuestos']} presupuestos."
        if stats["errores"]:
            msg += " Detalles: " + "; ".join(stats["errores"][:5])
        flash(msg, "ok" if not stats["errores"] else "error")
    except Exception as e:
        db.session.rollback()
        flash(f"Error importando: {e}", "error")
    return redirect(url_for("main.clientes"))


# ---------------- Parámetros / años ----------------
def _asesorias_filas(cli, a, maestro_previo=None):
    """Filas de asesorias del cliente con PLATA REAL para el ano activo.
    - Tarifas fijas: valor estandar (o editado) x cantidad.
    - Porcentajes: pct estandar (o editado) x base; base = renta_base guardada
      del cliente; si no hay, se deriva del presupuesto:
      base = (presupuesto - suma(fijas incluidas)) / (suma(% incluidas) / 100).
    Devuelve (filas, base_usada). Marca lo que viene del maestro."""
    if not a:
        return [], 0.0
    from .maestro import leer_maestro
    items = (AsesoriaCatalogo.query.filter(AsesoriaCatalogo.activo == True)
             .order_by(AsesoriaCatalogo.orden, AsesoriaCatalogo.id).all())
    guardadas = {x.asesoria_id: x for x in
                 (AsesoriaCliente.query.join(AsesoriaCatalogo)
                  .filter(AsesoriaCliente.cliente_id == cli.id).all())}
    nit = (cli.nit or "").strip()
    datos = {}
    if nit:
        if maestro_previo is not None:
            bruto = maestro_previo
        else:
            m = leer_maestro(a.anio_cobro, a.anio_gravable, {nit})
            bruto = (m or {}).get(nit, {})
        cod2id = {c.codigo: c.id for c in AsesoriaCatalogo.query.all()}
        datos = {cod2id[k]: v for k, v in bruto.items() if k in cod2id}
    p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
    presup = float(p.valor or 0) if p else 0.0

    pre = []
    sum_fijas = 0.0
    sum_pct = 0.0
    for it in items:
        if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
            continue
        x = guardadas.get(it.id)
        sugerido = it.id in datos
        incluir = bool(x.incluir) if x else sugerido
        fija = bool(it.es_fija)
        if fija:
            val = x.valor if (x and x.valor is not None and x.valor > 0) \
                else float(it.defecto_valor or 0)
            cant = (x.cantidad if (x and x.cantidad) else None) or 1
            sub = val * cant if incluir else 0.0
            if incluir:
                sum_fijas += sub
            pre.append(dict(it=it, x=x, incluir=incluir, fija=True,
                            eff_val=val, cant=cant, sub=sub, sugerido=sugerido))
        else:
            pct = x.pct if (x and x.pct is not None and x.pct > 0) \
                else float(it.defecto_pct or 0)
            if incluir:
                sum_pct += pct
            pre.append(dict(it=it, x=x, incluir=incluir, fija=False,
                            eff_pct=pct, cant=None, sub=0.0, sugerido=sugerido))
    base = float(cli.renta_base or 0)
    if base <= 0 and sum_pct > 0:
        base = max(0.0, (presup - sum_fijas) / (sum_pct / 100.0))
    filas = []
    for f in pre:
        if not f["fija"]:
            f["sub"] = round(f["eff_pct"] / 100.0 * base, 2) if (f["incluir"] and base > 0) else 0.0
        d = datos.get(f["it"].id)
        filas.append({
            "it": f["it"], "incluir": f["incluir"], "fija": f["fija"],
            "pct": (f["x"].pct if (f["x"] and f["x"].pct is not None) else None),
            "valor": (f["x"].valor if (f["x"] and f["x"].valor is not None) else None),
            "cantidad": (f["x"].cantidad if (f["x"] and f["x"].cantidad) else None),
            "eff_pct": (f["eff_pct"] if not f["fija"] else None),
            "eff_val": (f["eff_val"] if f["fija"] else None),
            "base": (round(base) if (not f["fija"] and base > 0) else None),
            "subtotal": f["sub"],
            "nota": ((f["x"].nota or "") if f["x"] else ""),
            "en_maestro": f["it"].id in datos,
            "estados": (d[1] if d else []),
            "cant_maestro": (d[0] if d else 0),
            "sugerido": f["sugerido"],
            "nueva": bool(f["sugerido"] and (f["x"] is None or not f["x"].incluir)),
        })
    return filas, round(base)


@bp.route("/asesorias", methods=["GET", "POST"])
def asesorias():
    """Catálogo estándar de asesorías (Parámetros → Asesorías)."""
    if request.method == "POST":
        f = request.form
        try:
            aid = int(f.get("id") or 0)
        except ValueError:
            aid = 0
        it = db.session.get(AsesoriaCatalogo, aid) if aid else None
        if not it:
            return jsonify(ok=False, error="asesoria inexistente")
        it.nombre = (f.get("nombre") or it.nombre).strip()[:120]
        it.tipo = f.get("tipo") if f.get("tipo") in ("PN", "PJ", "TODOS") else it.tipo
        try:
            it.defecto_pct = float(f.get("pct") or 0)
            it.defecto_valor = float(f.get("valor") or 0)
        except ValueError:
            pass
        it.base_min = (f.get("base_min") or "").strip()[:60]
        db.session.commit()
        return jsonify(ok=True)
    items = (AsesoriaCatalogo.query.order_by(AsesoriaCatalogo.orden, AsesoriaCatalogo.id).all())
    return render_template("asesorias_catalogo.html", items=items)


@bp.route("/clientes/<int:cid>/asesorias", methods=["POST"])
def cliente_asesorias(cid):
    """Guarda las asesorías del cliente (checkbox + % o valor por línea)."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    aid = request.form.get("asesoria_id", type=int)
    it = db.session.get(AsesoriaCatalogo, aid) if aid else None
    if not it:
        return jsonify(ok=False, error="asesoria inexistente")
    x = AsesoriaCliente.query.filter_by(cliente_id=cid, asesoria_id=aid).first()
    incluir = request.form.get("incluir") == "1"
    if x is None:
        x = AsesoriaCliente(cliente_id=cid, asesoria_id=aid)
        db.session.add(x)
    x.incluir = incluir
    nota = (request.form.get("nota") or "").strip()
    if nota or x.nota:
        x.nota = nota[:120]
    pct = (request.form.get("pct") or "").strip()
    val = (request.form.get("valor") or "").strip()
    x.pct = float(pct) if pct else None
    x.valor = float(val) if val else None
    cant = (request.form.get("cantidad") or "").strip()
    if cant:
        try:
            x.cantidad = max(1, int(float(cant)))
        except ValueError:
            pass
    elif it.es_fija and not x.cantidad:
        x.cantidad = 1
    db.session.commit()
    # Python es la unica calculadora: se devuelve el estado completo autoritativo
    return jsonify(ok=True, **_estado_asesorias(cli, anio_actual()))


def _estado_asesorias(cli, a):
    """Snapshot autoritativo del paquete del cliente. TODA la matematica vive aqui
    (Python); el front solo pinta. Base, subtotales, total, sobra y confirmacion."""
    filas, base = _asesorias_filas(cli, a)
    presup = 0.0
    if a:
        p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
        presup = float(p.valor or 0) if p else 0.0
    total = sum(f["subtotal"] for f in filas)
    delta = presup - total
    if presup <= 0:
        sobra = None
    elif delta > 1000:
        sobra = ["falta", round(delta)]
    elif delta < -1000:
        sobra = ["pasa", round(-delta)]
    else:
        sobra = ["ok", 0]
    from .maestro import bd_maestro
    confirmado = bool(a and db.session.query(PresupuestoHistorial.id)
                      .filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first())
    return {
        "base": float(base or 0),
        "presup": presup,
        "total": round(float(total)),
        "sobra": sobra,
        "maestro_ok": bool(bd_maestro()),
        "confirmado": confirmado,
        "filas": [{"id": f["it"].id, "incluir": bool(f["incluir"]), "fija": bool(f["fija"]),
                   "pct": f["pct"], "valor": f["valor"], "cantidad": f["cantidad"],
                   "nota": f.get("nota", ""),
                   "sub": round(float(f["subtotal"] or 0)),
                   "en_maestro": bool(f["en_maestro"])} for f in filas],
    }


@bp.route("/clientes/<int:cid>/asesorias-estado", methods=["GET"])
def cliente_asesorias_estado(cid):
    """Estado autoritativo del paquete (la pantalla pinta lo que esto responde)."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    return jsonify(ok=True, **_estado_asesorias(cli, anio_actual()))


@bp.route("/clientes/<int:cid>/asesorias-recalcular", methods=["POST"])
def cliente_asesorias_recalcular(cid):
    """Recalcula la renta base para que el paquete cuadre con el presupuesto
    (fijas primero, la base absorbe el resto). Python calcula, el front pinta."""
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    filas, _base = _asesorias_filas(cli, a)
    p = PresupuestoCliente.query.filter_by(cliente_id=cli.id, anio_cobro=a.anio_cobro).first()
    presup = float(p.valor or 0) if p else 0.0
    fijas = sum(f["subtotal"] for f in filas if f["incluir"] and f["fija"])
    sumpct = sum((f["eff_pct"] or 0) for f in filas if f["incluir"] and not f["fija"])
    if sumpct > 0 and presup > 0:
        nueva = max(0.0, round((presup - fijas) / (sumpct / 100.0), 2))
        cli.renta_base = nueva
        db.session.commit()
    return jsonify(ok=True, base_ajustada=True, **_estado_asesorias(cli, a))


@bp.route("/clientes/<int:cid>/paquete-calc", methods=["POST"])
def cliente_paquete_calc(cid):
    """Calculadora PURA del paquete (ficha y modal): base + marcas -> subtotales
    y total. NO escribe nada en la BD; sirve de vista previa en vivo."""
    import json as _json
    from flask import jsonify
    cli = db.get_or_404(Cliente, cid)
    a = anio_actual()
    if not a:
        return jsonify(ok=False, error="No hay año activo")
    try:
        base = float(request.form.get("base") or 0)
    except (TypeError, ValueError):
        base = 0.0
    try:
        marcas = {int(m.get("id")): m for m in _json.loads(request.form.get("marcas") or "[]")
                  if isinstance(m, dict) and m.get("id")}
    except (TypeError, ValueError):
        marcas = {}
    items = (AsesoriaCatalogo.query.filter(AsesoriaCatalogo.activo == True)
             .order_by(AsesoriaCatalogo.orden, AsesoriaCatalogo.id).all())
    salida, total = [], 0.0
    for it in items:
        if it.tipo != "TODOS" and it.tipo != (cli.tipo or "PN"):
            continue
        m = marcas.get(it.id)
        if m is None or not m.get("incluir"):
            salida.append({"id": it.id, "sub": 0.0})
            continue
        if it.es_fija:
            val = 0.0
            if m.get("valor") not in (None, ""):
                try:
                    val = float(m.get("valor"))
                except (TypeError, ValueError):
                    val = 0.0
            if val <= 0:
                val = float(it.defecto_valor or 0)
            try:
                cant = max(1, int(float(m.get("cantidad") or 1)))
            except (TypeError, ValueError):
                cant = 1
            sub = val * cant
        else:
            pct = 0.0
            if m.get("pct") not in (None, ""):
                try:
                    pct = float(m.get("pct"))
                except (TypeError, ValueError):
                    pct = 0.0
            if pct <= 0:
                pct = float(it.defecto_pct or 0)
            sub = pct / 100.0 * base
        salida.append({"id": it.id, "sub": round(sub, 2)})
        total += sub
    return jsonify(ok=True, filas=salida, total=round(float(total)))


def _paquete_objetivo(cli, a):
    """Paquete objetivo del cliente: lo que la oficina considero cobrar.
    Es la MISMA matematica de _asesorias_filas aplicada a las marcas actuales
    (marcas = paquete acordado; el cobro real es lo emitido en cuentas)."""
    filas, _base = _asesorias_filas(cli, a)
    return round(sum(f["subtotal"] for f in filas if f["incluir"]), 2)


def _cobrado_del_anio(a):
    """{cliente_id: valor} COMPROMETIDO en cuentas: lineas ACTIVAS de cuentas
    ENVIADA o PAGADA. BORRADOR no compromete; ANULADA no cuenta.
    OJO: no es plata recibida; lo recibido vive en Pago/_pagado_del_anio."""
    emis = (CuentaCobro.query.filter(CuentaCobro.anio_cobro_id == a.id,
                                     CuentaCobro.estado.in_(["ENVIADA", "PAGADA"]))
            .join(CuentaLinea).filter(CuentaLinea.estado == "ACTIVA")
            .options(db.contains_eager(CuentaCobro.lineas)).all())
    cob = {}
    for c in emis:
        for l in c.lineas:
            if l.estado == "ACTIVA":
                cob[l.cliente_id] = cob.get(l.cliente_id, 0.0) + float(l.valor or 0)
    return cob


def _pagado_del_anio(a):
    """{cliente_id: valor} PAGADO real: suma de pagos registrados en cuentas
    ENVIADA o PAGADA (los abonos de cuentas anuladas no cuentan).
    En cuentas de varios miembros el pago se reparte proporcional al valor
    de la linea de cada uno (misma proporcion que la cuenta)."""
    cts = (CuentaCobro.query.filter(CuentaCobro.anio_cobro_id == a.id,
                                    CuentaCobro.estado.in_(["ENVIADA", "PAGADA"])).all())
    if not cts:
        return {}
    ids = [c.id for c in cts]
    pagos_cta = {}
    for cid_, v in (db.session.query(Pago.cuenta_id, Pago.valor)
                    .filter(Pago.cuenta_id.in_(ids)).all()):
        pagos_cta[cid_] = pagos_cta.get(cid_, 0.0) + float(v or 0)
    lineas_cta = {}
    for cid_, cli_, v in (db.session.query(CuentaLinea.cuenta_id, CuentaLinea.cliente_id, CuentaLinea.valor)
                          .filter(CuentaLinea.cuenta_id.in_(ids),
                                  CuentaLinea.estado == "ACTIVA").all()):
        lineas_cta.setdefault(cid_, []).append((cli_, float(v or 0)))
    pag = {}
    for cid_, total_c in pagos_cta.items():
        base = sum(v for _, v in lineas_cta.get(cid_, []))
        if base <= 0:
            continue
        for cli_, lv in lineas_cta[cid_]:
            pag[cli_] = pag.get(cli_, 0.0) + total_c * (lv / base)
    return pag


def _filas_auditoria(a):
    """Filas de auditoria del anio: debio (paquete del motor) vs comprometido
    (cuentas ENVIADA/PAGADA) + pagado real (pagos registrados).
    SIN_EMITIR = paquete definido pero sin cuenta emitida todavia (no es error,
    es pendiente). FUERA_DE_PAQUETE = comprometido sin paquete (ej. trabajos adicionales).
    El maestro se lee UNA vez para todos los NITs (rendimiento)."""
    cobrado = _cobrado_del_anio(a)
    pagados = _pagado_del_anio(a)
    activos = {c.id: c for c in Cliente.query.filter_by(activo=True).all()}
    nits = {(c.nit or "").strip() for c in activos.values()} - {""}
    from .maestro import leer_maestro
    m_all = leer_maestro(a.anio_cobro, a.anio_gravable, nits) or {}
    filas = []
    for cid in set(cobrado) | set(activos):
        cli = activos.get(cid)
        if cli is None:
            continue
        f_cli, _b = _asesorias_filas(cli, a,
                                     maestro_previo=m_all.get((cli.nit or "").strip(), {}))
        debio = round(sum(f["subtotal"] for f in f_cli if f["incluir"]), 2)
        cob = round(cobrado.get(cid, 0.0), 2)
        pag = round(pagados.get(cid, 0.0), 2)
        if debio <= 1000 and cob <= 1000:
            continue
        dif = round(cob - debio, 2)
        if cob <= 1000:
            estado = "SIN_EMITIR"
        elif debio <= 1000:
            estado = "FUERA_DE_PAQUETE"
        elif dif < -1000:
            estado = "COBRADO_DE_MENOS"
        elif dif > 1000:
            estado = "COBRADO_DE_MAS"
        else:
            estado = "OK"
        filas.append({"cli": cli, "debio": debio, "cobrado": cob, "pagado": pag,
                      "dif": dif, "estado": estado})
    filas.sort(key=lambda f: f["cli"].nombre.lower())
    return filas


@bp.route("/auditoria", methods=["GET"])
def auditoria():
    """Fase C: debio cobrarse (paquete del motor) vs comprometido (ENVIADA+PAGADA)
    y pagado real (pagos registrados)."""
    a = anio_actual()
    if not a:
        flash("Activa un año de cobro primero.", "error")
        return redirect(url_for("main.dashboard"))
    filas = _filas_auditoria(a)
    comparables = [f for f in filas if f["estado"] != "SIN_EMITIR"]
    total_debio = round(sum(f["debio"] for f in comparables), 2)
    total_cob = round(sum(f["cobrado"] for f in comparables), 2)
    total_pag = round(sum(f["pagado"] for f in comparables), 2)
    sin_emitir = [f for f in filas if f["estado"] == "SIN_EMITIR"]
    return render_template("auditoria.html", a=a, filas=comparables,
                           sin_emitir=sin_emitir,
                           total_debio=total_debio, total_cobrado=total_cob,
                           total_pagado=total_pag)


@bp.route("/auditoria.xlsx", methods=["GET"])
def auditoria_xlsx():
    """Excel de auditoria del anio: 1 fila por cliente."""
    a = anio_actual()
    if not a:
        flash("Activa un año de cobro primero.", "error")
        return redirect(url_for("main.cuentas"))
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    filas = _filas_auditoria(a)
    wb = Workbook()
    h1 = Font(bold=True, color="FFFFFFFF")
    fill = PatternFill("solid", fgColor="FF6D28D9")
    ws = wb.active
    ws.title = "Auditoria"
    ws.append(["Código", "Cliente", "Debió cobrarse", "Comprometido (ENVIADA+PAGADA)",
               "Pagado (pagos reales)", "Diferencia", "Estado"])
    for col, wdt in enumerate([8, 38, 16, 24, 18, 13, 20], 1):
        ws.column_dimensions[get_column_letter(col)].width = wdt
        ws.cell(row=1, column=col).font = h1
        ws.cell(row=1, column=col).fill = fill
    rojo = Font(color="FF9C0006")
    verde = Font(color="FF006100")
    gris = Font(color="FF808080")
    naranja = Font(color="FFB45F06")
    ETIQ = {"OK": "OK", "COBRADO_DE_MENOS": "COBRADO DE MENOS",
            "COBRADO_DE_MAS": "COBRADO DE MÁS", "FUERA_DE_PAQUETE": "FUERA DE PAQUETE",
            "SIN_EMITIR": "SIN EMITIR", "PENDIENTE_PAGO": "PENDIENTE DE PAGO"}
    for f in filas:
        ws.append([f["cli"].codigo, f["cli"].nombre, f["debio"], f["cobrado"],
                   f["pagado"], f["dif"], ETIQ.get(f["estado"], f["estado"])])
        r_ = ws.max_row
        if f["estado"] == "COBRADO_DE_MENOS":
            ws.cell(row=r_, column=6).font = rojo
        elif f["estado"] == "COBRADO_DE_MAS":
            ws.cell(row=r_, column=6).font = verde
        elif f["estado"] == "SIN_EMITIR":
            ws.cell(row=r_, column=6).font = gris
            ws.cell(row=r_, column=7).font = gris
        if f["pagado"] + 1 < f["cobrado"]:
            ws.cell(row=r_, column=5).font = naranja
            ws.cell(row=r_, column=7).font = naranja
    tot_d = sum(f["debio"] for f in filas if f["estado"] != "SIN_EMITIR")
    tot_c = sum(f["cobrado"] for f in filas)
    tot_p = sum(f["pagado"] for f in filas)
    ws.append(["", "TOTALES (cuentas emitidas)", tot_d, tot_c, round(tot_p, 2),
               round(tot_c - tot_d, 2), ""])
    for col_ in (3, 4, 5, 6, 7):
        ws.cell(row=ws.max_row, column=col_).font = Font(bold=True)
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"Auditoria_{a.prefijo}_{date.today().isoformat()}.xlsx"
    return Response(buf, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={nombre}"})


@bp.route("/parametros", methods=["GET", "POST"])
def parametros():
    a = anio_actual()
    if request.method == "POST":
        f = request.form
        # solo se actualizan los campos que vengan en el formulario (a prueba de
        # posts parciales: lo que no viene, NO se borra)
        for k in ("emisor_nombre", "emisor_cc", "emisor_direccion", "emisor_telefonos",
                  "emisor_ciudad", "emisor_email", "formas_pago", "carpeta_pdfs",
                  "carpeta_correos", "carpeta_imagenes"):
            if k in f:
                Parametro.set(k, f.get(k, ""))
        if "ruta_casa" in f:
            Parametro.set("ruta_casa", f.get("ruta_casa", ""))
        if "ruta_oficina" in f:
            Parametro.set("ruta_oficina", f.get("ruta_oficina", ""))
        if "excel_cobros_anterior" in f:
            Parametro.set("excel_cobros_anterior", f.get("excel_cobros_anterior", ""))
        if "banco_info" in f:
            Parametro.set("banco_info", f.get("banco_info", "").replace("\r\n", "\n"))
        if a:
            if "anio_gravable" in f:
                a.anio_gravable = int(f.get("anio_gravable") or a.anio_gravable)
            if "prefijo" in f:
                a.prefijo = f.get("prefijo", a.prefijo)
            if "ipc" in f:
                a.ipc = float(f.get("ipc") or 0)
            if "valor_minima" in f:
                a.valor_minima = float(f.get("valor_minima") or 0)
            if "valor_minima_primera" in f:
                _basica_antes = float(a.valor_minima_primera or 0)
                a.valor_minima_primera = float(f.get("valor_minima_primera") or 0)
                # Tarifario: si cambia la Basica, los rangos 2+ siguen su factor
                if _basica_antes > 0 and a.valor_minima_primera > 0 and abs(a.valor_minima_primera - _basica_antes) > 0.5:
                    from .models import EstratoTarifa
                    for _e in (EstratoTarifa.query.filter(EstratoTarifa.factor.isnot(None),
                                                          EstratoTarifa.orden >= 2)
                               .all()):
                        _e.valor = piso_5000(a.valor_minima_primera * _e.factor)
            if "concepto" in f:
                a.concepto = f.get("concepto", "")
        db.session.commit()
        flash("Parámetros guardados", "ok")
        return redirect(url_for("main.parametros"))
    ub, rc, ro = _ubicacion_datos()
    return render_template("parametros.html", a=a, ubicacion=ub,
                           ruta_casa=rc, ruta_oficina=ro)


def _archivo_ubicacion():
    """Archivo LOCAL por PC donde vive la ubicación activa (no va en la BD:
    la BD se sincroniza por OneDrive y llegaría la ubicación del otro PC)."""
    d = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SistemaCobros")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "ubicacion.txt")


def _ubicacion_datos():
    """(ubicacion_activa, ruta_casa, ruta_oficina). La ubicación vive en archivo local
    por PC (como el Maestro con su config): la primera vez se autodetecta por la ruta
    que exista en este PC; después el toggle la cambia con 1 clic y cada PC se acuerda."""
    rc = (Parametro.get("ruta_casa", "") or "").strip()
    ro = (Parametro.get("ruta_oficina", "") or "").strip()
    ub = ""
    try:
        with open(_archivo_ubicacion(), encoding="utf-8") as fh:
            ub = fh.read().strip().upper()
    except OSError:
        pass
    if ub not in ("CASA", "OFICINA"):
        # autodetección: gana la ruta que exista en este PC; si no, la letra conocida
        if rc and os.path.isdir(_rebase(rc)):
            ub = "CASA"
        elif ro and os.path.isdir(_rebase(ro)):
            ub = "OFICINA"
        elif os.path.isdir("Z:\\"):
            ub = "CASA"
        elif os.path.isdir("C:\\Users"):
            ub = "OFICINA"
        else:
            ub = ""
        if ub:
            _guardar_ubicacion(ub)
    return ub, rc, ro


def _guardar_ubicacion(ub):
    try:
        with open(_archivo_ubicacion(), "w", encoding="utf-8") as fh:
            fh.write(ub)
    except OSError:
        pass


def _ruta_maestro_activa():
    """Ruta del maestro según la ubicación activa (sin mezclar rutas del otro PC)."""
    ub, rc, ro = _ubicacion_datos()
    if ub == "CASA" and rc:
        return _rebase(rc)
    if ub == "OFICINA" and ro:
        return _rebase(ro)
    general = _rebase(Parametro.get("ruta_maestro", ""))
    if general:
        return general
    return rutas_comunes.ruta_maestro_defecto()


@bp.route("/parametros/ubicacion", methods=["POST"])
def parametros_ubicacion():
    """Toggle CASA <-> OFICINA (1 clic, como en el Maestro). Se guarda LOCAL en este PC."""
    actual, rc, ro = _ubicacion_datos()
    nuevo = "OFICINA" if actual == "CASA" else "CASA"
    _guardar_ubicacion(nuevo)
    activa = _ruta_maestro_activa()
    ok = bool(activa and os.path.isdir(activa))
    flash(f"Ubicación cambiada a {nuevo} (guardada en este PC)."
          + (" Ruta del maestro encontrada." if ok
             else " Ojo: la ruta del maestro de esa ubicación no existe en este PC; revísala en Parámetros."),
          "ok" if ok else "error")
    return redirect(url_for("main.parametros"))


def piso_5000(x):
    """Redondeo a la BAJA a multiplos de 5.000 (a favor del cliente)."""
    import math
    return int(math.floor(float(x or 0) / 5000.0)) * 5000


@bp.app_context_processor
def _inyectar_tarifario():
    """Tarifario en TODAS las paginas (modal del navbar). Consulta, no edita."""
    try:
        from .models import AsesoriaCatalogo, EstratoTarifa
        return {
            "estratos_tarifa": EstratoTarifa.query.order_by(EstratoTarifa.orden).all(),
            "catalogo_tarifa": (AsesoriaCatalogo.query.filter_by(activo=True)
                                .order_by(AsesoriaCatalogo.orden, AsesoriaCatalogo.id).all()),
        }
    except Exception:
        return {"estratos_tarifa": [], "catalogo_tarifa": []}


@bp.route("/tarifario", methods=["GET", "POST"])
def tarifario():
    """Tarifario completo: renta por patrimonio (editable) + catalogo (lectura)."""
    from .models import AsesoriaCatalogo, EstratoTarifa
    if request.method == "POST":
        from flask import jsonify
        if request.form.get("acc") == "guardar":
            import json as _json
            try:
                datos = _json.loads(request.form.get("filas") or "[]")
            except ValueError:
                datos = []
            if not isinstance(datos, list) or not datos:
                return jsonify(ok=False, error="No recibí filas válidas")

            def _f(x):
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return None

            EstratoTarifa.query.delete()
            orden = 0
            for d in datos:
                if not isinstance(d, dict):
                    continue
                orden += 1
                pmin, pmax = _f(d.get("pat_min")), _f(d.get("pat_max"))
                factor, valor = _f(d.get("factor")), _f(d.get("valor"))
                db.session.add(EstratoTarifa(
                    orden=orden,
                    nombre=(d.get("nombre") or f"Estrato {orden}").strip()[:60],
                    pat_min=(pmin * 1000000.0 if pmin is not None else None),
                    pat_max=(pmax * 1000000.0 if pmax not in (None, "") else None),
                    valor=(piso_5000(valor) if valor is not None else None),
                    factor=(factor if (factor is not None and factor > 0) else None),
                    activo=True))
            db.session.commit()
            return jsonify(ok=True)
        return redirect(url_for("main.tarifario"))
    es = EstratoTarifa.query.order_by(EstratoTarifa.orden).all()
    cat = (AsesoriaCatalogo.query.filter_by(activo=True)
           .order_by(AsesoriaCatalogo.orden, AsesoriaCatalogo.id).all())
    a = anio_actual()
    return render_template("tarifario.html", estratos=es, catalogo=cat, a=a,
                           especial=(float(a.valor_minima or 0) if a else 0.0),
                           basica=(float(a.valor_minima_primera or 0) if a else 0.0))


@bp.route("/anios")
def anios():
    return render_template("anios.html",
                           anios=AnioCobro.query.order_by(AnioCobro.anio_cobro.desc()).all())


@bp.route("/anios/nuevo", methods=["POST"])
def anio_nuevo():
    f = request.form
    anio_cobro = int(f.get("anio_cobro"))
    anterior = AnioCobro.query.order_by(AnioCobro.anio_cobro.desc()).first()
    ipc = float(f.get("ipc") or 0)
    nuevo = AnioCobro(
        anio_cobro=anio_cobro,
        anio_gravable=anio_cobro - 1,
        prefijo=str(anio_cobro)[2:],
        ipc=ipc,
        valor_minima=(anterior.valor_minima * (1 + ipc)) if anterior else 0,
        valor_minima_primera=(anterior.valor_minima_primera * (1 + ipc)) if anterior else 0,
        concepto=f"Asesoría tributaria año gravable {anio_cobro - 1}",
        emisor_nombre=anterior.emisor_nombre if anterior else "",
        emisor_cc=anterior.emisor_cc if anterior else "",
        emisor_direccion=anterior.emisor_direccion if anterior else "",
        emisor_telefonos=anterior.emisor_telefonos if anterior else "",
        emisor_ciudad=anterior.emisor_ciudad if anterior else "",
        banco_info=anterior.banco_info if anterior else "",
        numero_siguiente=1, consecutivo_inicial=1, activo=False,
    )
    db.session.add(nuevo)
    # Tarifario: los estratos escalan con el IPC del nuevo año (a la baja, múltiplos de 5.000)
    if ipc:
        from .models import EstratoTarifa
        for _e in EstratoTarifa.query.filter(EstratoTarifa.valor.isnot(None)).all():
            _e.valor = piso_5000(_e.valor * (1.0 + ipc))
        db.session.commit()
    # arrastre: presupuesto nuevo = valor de la última cuenta emitida (o presupuesto si nunca se emitió)
    if anterior:
        for cli in Cliente.query.filter_by(activo=True):
            ult = (CuentaLinea.query.join(CuentaCobro)
                   .filter(CuentaLinea.cliente_id == cli.id,
                           CuentaCobro.anio_cobro_id == anterior.id,
                           CuentaLinea.estado == "ACTIVA",
                           CuentaCobro.estado.in_(("ENVIADA", "PAGADA")))
                   .order_by(CuentaCobro.numero.desc()).first())
            base = None
            if ult:
                base = ult.valor
            else:
                p = PresupuestoCliente.query.filter_by(cliente_id=cli.id,
                                                       anio_cobro=anterior.anio_cobro).first()
                base = p.valor if p else None
            if base:
                db.session.add(PresupuestoCliente(cliente_id=cli.id, anio_cobro=anio_cobro,
                                                  valor=round(base * (1 + ipc), -2)))
    db.session.commit()
    flash(f"Año {anio_cobro} creado con arrastre IPC {ipc:.1%}. Revísalo y actívalo.", "ok")
    return redirect(url_for("main.anios"))


@bp.route("/anios/<int:aid>/activar", methods=["POST"])
def anio_activar(aid):
    AnioCobro.query.update({AnioCobro.activo: False})
    a = db.session.get(AnioCobro, aid)
    if a:
        a.activo = True
    db.session.commit()
    return redirect(url_for("main.anios"))


# ---------------- Importación ----------------
@bp.route("/importar", methods=["GET", "POST"])
def importar():
    if request.method == "GET":
        return render_template("importar.html")
    f = request.files.get("archivo")
    if not f or not f.filename:
        flash("Selecciona el archivo Excel", "error")
        return redirect(url_for("main.importar"))
    os.makedirs(current_app.instance_path, exist_ok=True)
    ruta = os.path.join(current_app.instance_path, "import.xlsx")
    f.save(ruta)
    from .importar import importar as do_import
    try:
        stats = do_import(ruta)
        flash(f"Importación lista: {stats['clientes']} clientes nuevos, "
              f"{stats['presupuestos']} presupuestos, {stats['cuentas']} cuentas del año actual.",
              "ok")
    except Exception as e:
        db.session.rollback()
        flash(f"Error importando: {e}", "error")
    return redirect(url_for("main.dashboard"))


# ---------------- API auxiliar ----------------
@bp.route("/api/clientes/valor/<int:cid>")
def api_valor_cliente(cid):
    a = anio_actual()
    p = PresupuestoCliente.query.filter_by(cliente_id=cid, anio_cobro=a.anio_cobro).first() if a else None
    return jsonify({"valor": p.valor if p else 0})