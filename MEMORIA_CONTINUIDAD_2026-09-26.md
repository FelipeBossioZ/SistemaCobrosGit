# MEMORIA DE CONTINUIDAD - 2026-09-26 (Etapa 0 lista, motor a continuacion)
**Hecha por:** SistemaCobrosCasa (agente) - sesion con Felipe, sabado 26/09/2026 ~08:30
**Estado:** Etapa 0 COMPLETADA y verificada. Motor de asesorias (Etapa 1) especificado, pendiente de codigo.

---

## 0. QUE SE HIZO HOY (Etapa 0)

### En el 777 (SistemaPruebas)
1. **Backup previo** de la BD: `Respaldos BD\cobros_antes_etapa0_2026-09-26.db`.
2. **Fix `numero_siguiente`**: 14 -> 24 (la copia de BD arrastro la 26-013 que ya fue borrada en prod; habia colision latente al crear cuenta nueva).
3. **Modulo nuevo `app/rutas_comunes.py`**: resuelve maestro y Excel anterior RELATIVOS a la carpeta del proyecto. Cero letras hard-codeadas.
4. **Modulo nuevo `app/respaldos.py`**: backup automatico al arrancar (`Respaldos BD\cobros_YYYY-MM-DD.db`, 1 por dia, retencion 30 dias) + `PRAGMA integrity_check`.
5. **Parches en `routes.py`**: import de rutas_comunes; `_ruta_maestro_activa()` ahora cae al default relativo si no hay rutas configuradas; importador de Excel 2025 usa default relativo.
6. **Parche en `__init__.py`**: gancho de respaldo al arrancar.
7. **`cobros_2025.py`**: eliminado EXCEL_DEFECTO con ruta C: hard-codeada (la ruta vieja YA ESTABA ROTA en casa; el Excel vive en `Sistema de Cobros\Recursos\`).
8. **Parametros**: campo nuevo "Excel del ano anterior" (override opcional); se ELIMINO el parametro viejo `excel_cobros_anterior` que apuntaba a C:\OneDriveOficina (estaba mandando encima del default).
9. **Git local** inicializado con commit inicial (ver punto 2).

### En produccion (Sistema de Cobros) - MINIMO, verificado con create_app
- `routes.py`: mismos 3 parches de fallback (respaldo previo en `Respaldo codigo 2026-09-26\routes.py.antes-fallback.bak`).
- `__init__.py`: gancho de respaldo al arrancar (respaldo previo incluido).
- Copiados `rutas_comunes.py` y `respaldos.py`.
- **NO se toco la BD de produccion. NO se arranco el servidor de produccion.**
- Pendiente que Felipe abra produccion con `iniciar.bat` y confirme que todo funciona (deberia: create_app probo factory + migraciones idempotentes + respaldo).

## 1. COMO FUNCIONAN LAS RUTAS AHORA (las 3 capas)
1. **Default relativo** (`rutas_comunes.py`): maestro = `..\1- PLANIFICACION OFICINA\2026\Sistema maestro\sistema-maestro-v7` desde la carpeta del proyecto; Excel = raiz de 6-Presupuestos o `Recursos\` (primer existente). Funciona igual con Z: o C:.
2. **Override manual** en Parametros (`ruta_maestro`, `ruta_casa`/`ruta_oficina`, `excel_cobros_anterior`): si esta lleno, manda.
3. **`_rebase()`**: red de seguridad si una ruta guardada del otro PC no existe aqui.

Autodeteccion de ubicacion (CASA/OFICINA) intacta, archivo local por PC en `%LOCALAPPDATA%\SistemaCobros\ubicacion.txt`.

## 2. GIT (nuevo, conectado a GitHub)
- **Remoto unico para ambos:** https://github.com/FelipeBossioZ/SistemaCobrosGit
- **Ramas:** `produccion` = codigo de produccion 5001 (commit c7ace5b, incluye Etapa 0). `pruebas777` = desarrollo (commits 37060fb inicial + dcac199 Etapa 0). Existe ademas `master` en GitHub porque es la rama default del repo; hoy apunta igual a produccion (ignorable).
- **Flujo acordado:** todo cambio NACE en pruebas777 -> cuando Felipe aprueba, se copia a produccion y se sube a la rama `produccion`.
- **Comandos tipo** (desde cualquier PC; las ramas locales YA coinciden con las remotas):
  - En SistemaPruebas (rama local `pruebas777`): `git add -A` + `git commit -m "..."` + `git push`
  - En Sistema de Cobros (rama local `produccion`): `git add -A` + `git commit -m "..."` + `git push`
- Estado 26/09: `pruebas777` = f79bca9 (Etapa 0 + Motor parte 1). `produccion` = `master` = c7ace5b (Etapa 0).
- `.gitignore` en ambos: excluye `instance/`, `__pycache__/`, `Respaldos BD/`, `Respaldo codigo */`, `salidas/`, `*.db`.
- **Las BD NO viajan por git** (siguen viajando por OneDrive, cada instalacion con la suya).
- **PC de oficina:** las carpetas llegan por OneDrive con su .git y remote ya configurados; no hay que clonar nada. Solo la PRIMERA vez que pida credenciales al hacer push, loguearse a GitHub (el Credential Manager de Windows las guarda).
- **Regla de oro:** trabajar de a un PC a la vez y `git push` al cerrar la sesion (el .git se sincroniza por OneDrive; evitar commits simultaneos en ambas maquinas).

## 3. VENV (respuesta a la duda de Felipe)
- `instalar_venv.bat` pregunta DONDE crear el venv (default `C:\EntornosPython\SistemaCobros-venv`), lo crea FUERA de OneDrive y escribe la ruta en `%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt` (archivo LOCAL por PC; OneDrive no lo sincroniza).
- Los .bat leen ese archivo local primero; `C:\EntornosPython\...` es solo fallback.
- Verificado hoy: **0 venvs dentro de 6-Presupuestos**. OneDrive esta limpio.
- Este PC (CASA): venv en `C:\Users\Usuario\Desktop\EntornosVirtuales\SistemaCobros` (Python 3.13.7).

## 4. ESTADO REAL DEL MOTOR (Etapa 1) - aprobado por Felipe, aun SIN codigo
Aprobaciones ya dadas (25/09 17:25 + 26/09):
- Catalogo % de renta vs tarifa fija; `cantidad` para tarifas fijas (IVA, RF, CONSUMO, ANTICIPO_RST base RF $100.000); 2516 lo ajusta Felipe a mano; CAMARA = REGISTRO_MERCANTIL; renta pendiente = aviso amarillo y marca lo demas.
- Faltan en la semilla: **ICA 50%, CONSUMO, ANTICIPO_RST, RUB 15%, SUPERSOC 75%, RST_SIMPLE (trata como renta)**.
- Botones: MASIVO (todos los clientes) + INDIVIDUAL por cliente en la ficha. Cada vez que se pulen, releen el maestro.
- El botón NO pisa datos existentes sin avisar; trae lo PRESENTADO del maestro y arma preliminar con base derivada del presupuesto.
- Nuevo (26/09): al lado de la sumatoria vs presupuesto va boton **Guardar/Confirmar**. Si la desviacion es de redondeo => deja el presupuesto igual. Si difiere de verdad y Felipe confirma => actualiza el presupuesto. Todo editable a mano antes de confirmar.
- Auditoria: primer guardado genera log automatico "Revision inicial". Cambios posteriores EXIGEN nota obligatoria (tabla `presupuesto_historial` ya existe en el 777).
- Regla C de C: BORRADOR/sin cuenta => flexible. ENVIADA/PAGADA => no se toca el valor ni el PDF; queda registro en photo card y Excel de reportes ("se cobro X, debio ser Y porque se le presento Z").
- Cliente no encontrado en maestro: marcarlo VISIBLE (color + nota "No encontrado en maestro") en la lista.
- Limpieza pendiente: 11 filas sucias en `asesorias_cliente` del 777 (pct con pesos adentro).

## 4b. MOTOR PARTE 1 - HECHO (26/09 ~09:30, en el 777, subido a GitHub)
- `asesorias_catalogo` + columna `es_fija` (True = tarifa fija x cantidad, False = % de renta base). 22 items: 11 por % (RENTA, RST_SIMPLE, IP, EXOGENA, EXO_MPIO, F2516, ACT_EXT, CAMARA, ICA, RUB, SUPERSOC, DEV=12 en realidad) y fijas (IVA, CONSUMO, ANTICIPO_RST, RF, FE_INS, FE_FAC, CONT_PN, CONT_PJ_B, CONT_PJ_C, OTRAS).
- `asesorias_cliente` + columna `cantidad` (default 1). `clientes` + columna `renta_base` (FLOAT, None = derivar del presupuesto).
- Semilla sincroniza es_fija de items viejos y agrega los que falten (idempotente).
- Limpieza: 11 filas sucias de `asesorias_cliente` eliminadas (la tabla quedo vacia y lista para el motor).
- Smoke test: app arriba, /parametros /asesorias /clientes/1 -> 200.
- Decisiones cerradas por Felipe: IVA/RF estandar propuesto y el baja a mano por cliente; RST_SIMPLE presentada cuenta como renta OK; tolerancia de redondeo fija +/- $1.000.

## 4c. MOTOR PARTE 2 - HECHO Y PROBADO (26/09 ~10:00, commit 9037bee)
- **`app/maestro.py` (nuevo):** lee obligaciones del maestro por NIT. Mapeo: RENTA=RENTA_PN/PJ, RST_SIMPLE=RST, IP=PATRIMONIO, EXO_MPIO=EXG_MED, F2516=FORMATO_2516/2517, CAMARA=REGISTRO_MERCANTIL, etc. Reglas de periodo: anuales = AG-<gravable> o AG-<anio_cobro>, o periodo vacio SOLO si scanner dice PRESENTADA/PAGADA (caso Cock: RST sin periodo); periodicos (IVA, RF, CONSUMO, ANTICIPO_RST, CAMARA) = periodo que empieza con el anio de cobro (cuenta cantidad).
- **Total en plata real:** la ficha ahora muestra subtotales en pesos. % de renta x BASE; base = renta_base guardada del cliente, si no existe se DERIVA del presupuesto: (presupuesto - fijas incluidas) / (suma % incluidos / 100). Tarifas fijas = valor x cantidad (cantidad editable, el masivo la llena con el conteo del maestro).
- **Boton "Traer del maestro"** en la ficha (individual) + **"Traer asesorias del maestro"** masivo en Clientes. Ambos releen el maestro cada vez, no pisan valores editados, marcan lo presentado y dejan badge verde "nuevo del maestro" en las filas nuevas.
- **Guardar/Confirmar** en la ficha: amarra la renta base del cliente; si total vs presupuesto difiere <= $1.000 o es igual, presupuesto se queda; si difiere de verdad, se actualiza. Log SIEMPRE en presupuesto_historial: primera vez nota automatica "Revision inicial", despues exige nota (modal). Segunda confirmacion sin nota devuelve pide_nota=true.
- **Badges en la lista de Clientes:** rojo "no encontrado en maestro" y amarillo "sin NIT - no en maestro" (visibles al voleo). Prueba del 26/09: 113 clientes con datos (151 filas), 56 sin datos en maestro, 1 sin NIT.
- **Photo card auditable:** columnas Tarifa/Cant./Subtotal, muestra base usada, y cinta verde "Auditado con el Sistema Maestro" cuando hay datos del maestro.
- **Pruebas reales hechas:** masivo -> 151 filas en 113 clientes (RENTA 101, IP 15, ACT_EXT 9, IVA 11, CAMARA 4, RST_SIMPLE 2 -incluye Christian Cock-, ICA 8, CONSUMO 1). Cliente 7 (Alvarez Londono Martha, pres. 1.920.000): base derivada 1.280.000, Renta 100% + IP 50% = 1.920.000 exacto; confirmar -> presupuesto intacto, renta_base 1.280.000 guardada, log "Revision inicial" creado.
- **BD del 777 quedo con datos de prueba reales** (asesorias_cliente poblada por el masivo + 1 confirmacion). Es el ambiente de pruebas: Felipe puede seguir probando sobre eso; si quiere partir de cero: borrar filas de asesorias_cliente, renta_base y presupuesto_historial (o pedirselo al agente).

### Falta (Fase C / pendientes del motor)
1. Excel exportable con columna "debio cobrarse X (sistema) vs cobrado Y" para cuentas ENVIADA/PAGADA (auditoria de cobros).
2. Prelleno del desglose estandar automatico (Fase C original: estados por asesoria desde maestro ya estan en la data; falta UI para estados individuales por obligacion).
3. Regla "renta pendiente = aviso amarillo" en la ficha (la data del maestro ya distingue PRESENTADA de pendiente; falta pintar el aviso).

## 4d. PAQUETE APROBADO 26/09 (~11:30, commit 7e2c2f1) - modal base + lapiz + revertir
Decisiones de Felipe (cerradas): 1) el presupuesto NUNCA se digita: se construye desde la BASE (base x marcas = presupuesto); los trabajos adicionales viven FUERA del presupuesto; 2) Contabilidad PN es TARIFA MENSUAL ($600.000/mes, Cant = meses); 3) SI al aviso de sobra del paquete; 4) al aceptar el modal nuevo se aplica TODO de una (base amarrada + marcas + presupuesto) y queda listo para photo card.
- **Modal "Construir desde la base"** (reemplaza el de valor digitado): campo base + lista completa con checkboxes + total en vivo; "Usar como presupuesto" aplica base, marcas y presupuesto en una transaccion; motivo obligatorio desde la 2a vez; regenera PDFs borrador / nota interna en ENVIADA-PAGADA. Ruta: POST /clientes/<id>/presupuesto-paquete (param opcional aplicar_marcas=0 para solo cambiar presupuesto). Sirve tambien para crear el PRIMER presupuesto de un cliente.
- **Columna % / valor BLOQUEADA**: lapiz junto al titulo habilita; se convierte en check verde (guardar) y X roja (cancelar). Sin cambios cierran sin preguntar; con cambios confirman. Los cambios se guardan todos juntos (POST /clientes/<id>/asesorias por fila). base.html: auto-guardado de la ficha ahora SOLO incluir/cantidad (los pct/valor van por el flujo del lapiz).
- **Bases parametrizadas en catalogo (seed una vez, no pisa ediciones):** IVA 150.000, CONSUMO 100.000, ANTICIPO_RST 100.000, RF 100.000, CONT_PN 600.000 "tarifa mensual". OTRAS queda la unica libre. Al marcar, el valor se llena con la base y Cant queda 1 o la del maestro.
- **Revertir al maestro** (POST /clientes/<id>/asesorias-revertir): apaga lo manual, deja solo lo presentado en el maestro, valores vuelven a estandar, cantidades desde el maestro; BLOQUEADO si ya hubo confirmacion del ano (historial existe). Repetible hasta Guardar.
- **Recalcular** (boton): re-deriva la base para que el paquete cuadre con el presupuesto (fijas primero, base absorbe el resto). Es obligatorio antes de Guardar: el front bloquea si hay cambios sin recalcular (pendiente) y el servidor devuelve requiere_recalculo si el paquete no cuadra (> $1.000).
- **Confirmar ya NUNCA toca el presupuesto.** Solo amarra base + log. El presupuesto cambia SOLO por el modal base.
- **Aviso de sobra en la ficha:** "Quedan $ X del presupuesto sin marcar" (amarillo) o "las marcas se pasan $ X" (rojo) junto a la base.
- **Pruebas hechas en 777:** Sergio (cid 25, codigo 65): revertir bloqueado tras confirmacion OK; paquete desde base 600.000 con Renta+IP -> presupuesto 1.000.000 exacto; confirmar dejo presupuesto intacto. Datos de Sergio RESTAURADOS al estado de la imagen 1 (marcas Renta/Exo/ActExt/RUB/IVA3/FEs, base 504.545, presup 1.660.000, historial 'RUB y otras no aplicaban' como unica entrada). NOTA: Martha (cid 7) quedo con presup 1.920.000 y base 1.280.000 confirmados (correcto); las FE marcadas de la prueba del paquete con base 600k fueron desmarcadas al restaurar Sergio.
- **Pendiente menor:** inputs ac-pct/ac-val llegan deshabilitados al HTML (pencil los habilita); el JS del ficha recalcula subtotales en vivo con la base del tfoot.

### Falta (Fase C / pendientes del motor)
1. Excel exportable con columna "debio cobrarse X (sistema) vs cobrado Y" para cuentas ENVIADA/PAGADA (auditoria de cobros).
2. Prelleno del desglose estandar automatico (Fase C original: estados por asesoria desde maestro ya estan en la data; falta UI para estados individuales por obligacion).
3. Regla "renta pendiente = aviso amarillo" en la ficha (la data del maestro ya distingue PRESENTADA de pendiente; falta pintar el aviso).
4. Felipe debe PROBAR el paquete en el 777 y aprobar para pasar a produccion.

## 4e. DESPLIEGUE A PRODUCCION (26/09 ~12:15, commit prod c2e83bf)
- Estrategia: SOLO app/ viajo (git checkout origin/pruebas777 -- app/ en el repo de produccion). Las BDs NO viajan: cada instalacion conserva la suya (pruebas quedo con data de prueba; produccion con asesorias_cliente y presupuesto_historial en 0).
- Respaldo previo: Respaldos BD/cobros_antes_motor_2026-09-26.db (110 KB).
- Verificaciones pre-despliegue: anios_cobro de produccion ya tenia numero_siguiente=13 y anio_gravable=2025 (el '1' visto era la col activo); MAX(numero) cuentas_cobro=23 (el codigo nuevo salta numeros usados, self-healing; no se tocaron datos).
- Migracion corrio via create_app (sin servidor): tablas asesorias_catalogo/asesorias_cliente/presupuesto_historial creadas, 22 items sembrados CON bases (IVA 150k, CONSUMO 100k, ANTICIPO 100k, RF 100k, CONT_PN 600k mensual). Smoke test: / /clientes /asesorias /parametros /clientes/1 -> 200.
- Push a origin/produccion OK (c7ace5b -> c2e83bf). PC OFICINA: al sincronizar OneDrive llega el .git; solo git pull (o nada, el working tree ya esta actualizado) + iniciar.bat.
- Pendiente verificacion de Felipe: abrir produccion con iniciar.bat, revisar ficha de un cliente real y el boton 'Construir desde la base'.

## 4f. PYTHON UNICA CALCULADORA (26/09 ~12:55, commit 793b59c, solo en 777)
- Respuestas de Felipe a la opinion honesta: (1) una sola persona, una PC a la vez OK; (2) SECRET_KEY lo ve despues; (3) duplicidad de formula -> SOLUCIONADA ahora; (4) quiere a futuro INTEGRAR el Sistema Maestro con este sistema en uno solo (el maestro fue pensado para todo: vencimientos, cobros, presupuestos) - proyecto grande aprobado en principio, planear despues; (5) Felipe no programa: las explicaciones tecnicas deben ser simples y las decisiones por preguntas concretas; (6) a futuro quiere delegar la operacion; (7) permiso dado para mover JS a Python.
- HECHO: la ficha YA NO CALCULA nada en JavaScript. Endpoints autoritativos nuevos: GET /clientes/<id>/asesorias-estado (snapshot completo: base, presup, total, sobra [falta|pasa|ok, monto], maestro_ok, confirmado, filas con sub), POST /clientes/<id>/asesorias-recalcular (ajusta renta_base con 2 DECIMALES para que el total cuadre exacto con el presupuesto), POST /clientes/<id>/paquete-calc (calculadora PURA del modal: base+marcas -> subtotales/total, no escribe BD). POST /clientes/<id>/asesorias ahora devuelve el estado completo. El JS solo envia cambios y pinta lo que responde Python (funcion pintar() desde estado).
- Hallazgo cosmético corregido: los subtotales traen centavos (Exo 378.408,75; ActExt 151.363,5; RUB 75.681,75) y suman 1.659.999 para Sergio vs 1.660.000 visual. Con base con centavos el total da exacto. La tolerancia ±$1.000 del confirmar cubre cualquier resto.
- Pendiente: PASAR ESTO A PRODUCCION junto con la proxima tanda (no se ha pasado el 793b59c; produccion queda en c2e83bf que todavia calcula en JS).

## 4g. PYTHON-CALC A PRODUCCION + FASE C ARRANCADA (26/09 ~13:55)
- Felipe aprobo el 793b59c y pidió pasar a producción Y de una vez hacer la Fase C (Excel auditoria debio-cobrarse-vs-cobrado). Integracion Maestro+Cobros: se empieza LA PROXIMA SEMANA.
- Produccion actualizada: c2e83bf -> 5b74ebf (solo routes.py + cliente_detalle.html; backups .antes-pythoncalc.bak en Respaldo codigo 2026-09-26; smoke test 200 en 6 rutas incluida /clientes/1/asesorias-estado con claves base/confirmado/filas/maestro_ok/ok/presup/sobra/total).
- FASE C (en construccion en 777): tabla ENVIADA/PAGADA del anio, por cliente: presupuesto vs paquete cobrado (cuentas ENVIADA+PAGADA del anio activo), columnas estado, debio (paquete al confirmar), cobrado (valor linea cliente), diferencia. Criterios definidos: 'debio' = suma de subtotales de asesorias al momento del primer confirmar del anio (aprox: presupuesto actual cuando no hay historial de paquete); PENDIENTE de validar con Felipe el caso 'aqui fue donde se cobro de menos' (Sergio 1.660.000 presup vs 1.054.545 cobrado).

## 4h. FASE C: AUDITORIA DEBIO-VS-COBRADO (26/09 ~14:40, en 777, pendiente aprobacion)
- NUEVO: pagina /auditoria (link en navbar), boton Excel /auditoria.xlsx, y bloque 'previo de cierre' al final del listado de clientes (solo con cuenta emitida + contador de sin emitir).
- Criterios: DEBIO = paquete del motor (suma subtotales de marcas actuales, misma matematica _asesorias_filas). COBRADO = lineas ACTIVAS de cuentas ENVIADA+PAGADA (BORRADOR no compromete; ANULADA no cuenta). Estados: OK (±$1.000) / COBRADO DE MENOS / COBRADO DE MÁS / FUERA DE PAQUETE (cobrado sin paquete) / SIN EMITIR (paquete sin cuenta; se lista aparte, no se compara).
- RENDIMIENTO: leer_maestro ahora admite lectura POR LOTES: _asesorias_filas(cli, a, maestro_previo={nit: datos}) evita 1 lectura sqlite por cliente. /auditoria y /clientes pasaron de ~70s a ~1s.
- Datos reales 777: 24 clientes con cuenta emitida (20 OK, 4 DE MENOS: Franco -10k, Muñoz -10k, Tobón A. -20k, Tobón M. -20k = descuentos/ajustes reales de cuentas 26-006/007/021), 93 SIN EMITIR. Totales comparables: debio 9.960.000 vs cobrado 9.900.000.
- Hallazgo pendiente de decidir: el modal guarda el total con centavos en PresupuestoCliente y las lineas de cuenta redondean -> el 'debio' puede diferir $1-2 del 'cobrado' por redondeo. Con ±$1.000 no molesta, pero si Felipe quiere clavado, guardar el debio REDONDEADO al confirmar el paquete o al emitir la cuenta.
- Backups: routes.py.faseC*.bak, clientes.html.faseC.bak, base.html.faseC.bak en Respaldo codigo 2026-09-26.

## 4i. FASE C A PRODUCCION + ACCIONES RAPIDAS CLIENTES (27/09, df331f7 en 777)
- Fase C paso a PRODUCCION (29ca9bd) con smoke test 200 en /auditoria y /auditoria.xlsx. Backups .antes-faseC.bak en Respaldo codigo produccion.
- PEDIDO FELIPE: en clientes, las acciones rapidas lo devolvian al inicio (perdia el lugar en la letra R). Ahora: el sobre se reemplazo por DOS botones fetch: sobre=correo (crea PDF+.eml juntos SIEMPRE, _generar_eml regenera el PDF, nunca falla por PDF faltante) y whatsapp=imagen (nueva ruta GET/POST /clientes/<id>/imagen, guarda PNG en carpeta_imagenes parametrizada; usa imagen_cuenta.generar_imagen: fitz->pdf2image->Pillow). NINGUNA accion rapida eliminada (rayo, editar, decl, cobrado siguen). Ambas responden JSON (request.accept_mimetypes), toast esquina inferior derecha, la pagina NO se recarga -> scroll y filtro del buscador se mantienen. Sin JS funcionan como antes (redirect/flash/download).
- OJO (lecciones): (1) anclas con caracteres unicode: el title del sobre tenia EMDASH U+2014 y el mensaje un rayo U+26A1 - usar repr() ANTES; (2) el title tenia un {% if %} interno y un corte por indices se lo comio -> rompio jinja (endif/endfor desbalanceados); reparar por delimitadores semanticos (nombre de funcion url_for siguiente), nunca cortar en el PRIMER endif tras un inicio; (3) al fallar un parche medio, el archivo puede quedar SIN guardar (los asserts protegen).
- Pendiente de probar por Felipe en 777: botones sobre/whatsapp del listado (deben mantener scroll y filtro), y la carpeta de imagenes en Parametros (carpeta_imagenes; vacia = carpeta de PDFs).

## 4j. RAYO POR FETCH (27/09 ~15:50, dfc32d5 en 777, pendiente produccion)
- Felipe reporto el caso real: Marcela Diaz Velez sin cuenta -> el rayo recargaba y lo devolvia al inicio. AHORA el rayo tambien trabaja en segundo plano: cliente_cuenta_expresa reescrita con helper _res(msg, tipo) que responde JSON (ok/mensaje o ok=false/error) cuando Accept: application/json, y redirect+flash si no (grupos y ficha siguen funcionando como antes). El form del listado lleva clase form-expreso + data-confirm (el texto del confirm viejo se traslado a data-confirm) + data-nombre; el JS intercepta submit, pide confirm, hace fetch POST y muestra toast. Scroll y filtro se mantienen SIEMPRE.
- Probado end-to-end: Marcela (cid 39, presupuesto 330.000) -> creo cuenta 26-025 con PDF+eml (ok JSON); segundo clic -> 'ya esta en la cuenta 26-025... usa el sobre'. Limpieza: cuenta 26-025 ANULADA con motivo, envios borrados, numero_siguiente=25 (sqlite directo; app.db no expone db en __init__).
- Flujo final de acciones rapidas en clientes: RAYO crea cuenta+PDF+eml / SOBRE crea PDF+eml de cuenta existente / WHATSAPP crea imagen PNG. Todo por fetch con toast; NADA recarga la pagina.
- PENDIENTE: pasar sobre+whatsapp+rayo-fetch a produccion cuando Felipe lo apruebe (produccion va en 29ca9bd).

## 4k. FALSO DUPLICADO + DESCARGA DE IMAGEN RESTAURADA (27/09 ~16:00, ddaf121 en 777)
- Felipe reporto: 'me creo una cuenta duplicada y no me descargo la imagen' (Marcela). Diagnostico con BD+carpetas: (1) NO hubo duplicado - a las 15:45 YO cree la 26-025 probando el rayo y la deje ANULADA; a las 15:51 Felipe dio rayo y el sistema correctamente creo la 26-026 (anulada no bloquea: esa es la regla anti-duplicacion; en BD Marcela tiene UNA cuenta viva). Leccion: despues de probar con datos reales, avisar explicitamente que quede 'como estaba' ANTES de que el usuario vea la pantalla - el residuo de prueba se confunde con un bug. (2) La imagen SI se creo (PNG 100KB en carpeta_imagenes de Parametros, ruta C:\OneDriveOficina\...\salidas\imagenes) pero YO habia quitado la descarga al navegador al pasarla a fetch - error de criterio: Felipe necesita la imagen a mano para adjuntarla en WhatsApp.
- FIX (ddaf121): cliente_imagen ahora guarda en carpeta Y devuelve send_file(png, as_attachment) con headers X-Nombre/X-Mensaje cuando Accept: application/json; el JS hace r.blob() + createObjectURL + a.click() -> descarga a Descargas SIN recargar (mantiene scroll/filtro). Sin JS sigue flash+redirect. Probado: status 200, Content-Type image/png, magic bytes PNG, headers correctos.
- Limpieza adicional: archivos de la prueba 26-025 (pdf+eml) movidos a Respaldo codigo 2026-09-26.
- PENDIENTE produccion: Fase C (29ca9bd ya esta) + acciones rapidas fetch (sobre/whatsapp/rayo) + descarga de imagen (ddaf121) cuando Felipe apruebe.

## 4l. ACCIONES RAPIDAS A PRODUCCION (27/09 16:20, e273066) + PREGUNTA AUDITORIA
- Felipe aprobo: pasamos rayo/sobre/WhatsApp por fetch a produccion. checkout origin/pruebas777 -- routes.py, clientes.html, base.html (65f2e6d); backups .antes-acciones.bak; py_compile OK; smoke test SOLO LECTURA con test_client en memoria (6 rutas 200; /correo y /imagen con cliente 1 que NO tiene lineas -> devolvieron el error JSON sin mutar nada; cero escritos en BD de produccion). Commit e273066 en rama produccion. Produccion queda: Fase C (29ca9bd) + acciones rapidas (e273066) = sync total con pruebas777 65f2e6d en app/.
- PREGUNTA DE FELIPE (respondida sin codigo): en Auditoria, los ENVIADOS marcan OK pero el dice 'COBRADO + PAGADO?'; muchos enviados no han pagado. EXPLICACION: COBRADO = deuda comprometida en cuentas ENVIADA+PAGADA (lineas ACTIVAS); PAGADO es otra cosa (dinero recibido, pagos), NO interviene en el OK. El OK solo dice: lo que cobraste (cuenta) = lo que debias cobrar (paquete del motor), +-1.000. Estado de pago se ve en Cuentas/Pagos. CANDIDATOS A ORGANIZAR (esperando decision de Felipe): (a) renombrar columna 'Cobrado' a 'Comprometido en cuenta' o 'Deuda en cuenta'; (b) agregar columna separada 'Pagado' (suma de pagos) y estado de pago por cliente; (c) en el Excel igual. NO IMPLEMENTAR hasta que Felipe diga.
- Nota tecnica para el futuro: si el smoke de produccion prueba /correo o /imagen, usar un cliente SIN lineas (como cid 1) para no mutar; con cliente con cuenta ENVIADA, /correo vuelve a generar .eml (sin nota nueva si ya habia envios) y puede cambiar estado solo de BORRADOR.

## 5. PREGUNTAS ABIERTAS (las respuestas llegan por chat)
Q1 renta base: ¿guardar al confirmar (recomendado, auditable) o derivar en vivo?
Q2 sin match en maestro: se marca y se lista (propuesto y aceptado en linea general: color + nota visible).
Q3 estandares viejos de IVA/RF por antiguedad: ¿el preliminar propone estandar y Felipe baja a mano, o migrar valores viejos?
Q4 RST_SIMPLE presentada: ¿cuenta como renta OK? (caso Christian Cock).
Q5 git en produccion: RESUELTO 26/09 - primer commit hecho y subido a GitHub (produccion + pruebas777).

## 6. PENDIENTOS MENORES
- Purga de `__pycache__` de OneDrive (hay .pyc 313 y 314 mezclados; el .gitignore ya no los versiona, falta excluirlos de sync si Felipe quiere).
- SMLV 2026: cuando salga el decreto, actualizar catálogo (CONT_PN, CONT_PJ_C).
- Prueba en el PC de OFICINA despues de que OneDrive sincronice: abrir 5001 y 777, verificar que rutas_comunes resuelve con la letra C (debe: es relativo).
