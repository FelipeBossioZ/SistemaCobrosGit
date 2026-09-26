# MEMORIA DEL PROYECTO — Sistema de Cobros

> Documento de continuidad. Última actualización: **lunes 15 de septiembre de 2026**.
> Sirve para retomar el desarrollo en cualquier PC (casa u oficina) sin perder contexto.

---

## 1. Qué es este proyecto

Sistema web (Flask + Python) para controlar las **Cuentas de Cobro** anuales de la oficina
de asesoría tributaria: quién ha pagado, quién no, medio y fecha de envío, cómo y cuándo
pagaron, abonos, autodescuentos y observaciones. Genera el PDF de la Cuenta de Cobro.

- **Dueño/usuario**: Felipe (oficina de contabilidad, Medellín). Un solo usuario, sin login.
- **Ciclo actual**: año gravable **2025** cobrado en **2026** → cuentas `26-001`, `26-002`…
- **Fase 1 completada y probada** (ver sección 5). Facturas DIAN quedan para Fase 3.

## 2. Ubicaciones y cómo correr

| Carpeta | Rol |
|---|---|
| `Z:\OneDrive\OFICINA\FELIPE\Oficina Felipe\6-Presupuestos\Sistema de Cobros` | **Carpeta de trabajo principal** (OneDrive casa⇄oficina) |
| `P:\...\MemoriaOpenClaw\Sistema de Cobros` | Respaldo espejo (copia original creada en casa) |

- **Arranque**: doble clic a `INICIAR.bat` → abre `http://localhost:5001`.
- **Puerto 5001** (el 5000 lo usa el sistema Maestro; 5678 contraseñas; 5173 Don Peppini Contadore).
- **Python real**: `C:\Python313\python.exe` (el `python` del PATH puede ser el empaquetado de
  AutoClaw que NO trae `venv`; el .bat ya lo resuelve solo). Si toca recrear el entorno:
  `C:\Python313\python.exe -m venv venv` y luego `venv\Scripts\python -m pip install -r requirements.txt`.
- **Base de datos**: `instance/cobros.db` (SQLite, un archivo = un respaldo).
- **PDFs generados**: `instance/pdfs/<año>/<prefijo>-<número>.pdf`.
- Si OneDrive queda sincronizando, cerrar el servidor antes de cambiar de PC.

## 3. Decisiones de negocio confirmadas por Felipe (13 preguntas, 13-sep-2026)

1. **Alcance Fase 1**: solo Cuentas de Cobro + pagos + dashboard. **Facturas y vencimientos NO** —
   "eso es un mundo aparte, no meterse con ese chicharrón todavía".
2. **Sin login**, un solo usuario. Corre en casa y en oficina vía OneDrive.
3. **Importación**: solo clientes **activos**, solo el ciclo actual. Lo retirado y años anteriores
   se depuran/fueran. Histórico viejo NO se carga.
4. **Ciclo**: gravable 2025 → cobro 2026, prefijo `26`, concepto del PDF
   "Asesoría tributaria año gravable 2025". Confirmado.
5. **Valores**: el sistema **propone** el valor (desde el Excel al importar; entre años por arrastre
   con IPC) y Felipe revisa/ajusta uno a uno.
6. **PDF**: diseño **más limpio, minimalista moderno** (no réplica del formato viejo). **Sin logo**.
7. **Numeración** `26-001, 26-002…` automática, reinicia cada año.
   **Anulación**: la cuenta queda ANULADA **conservando el número** — nunca se reutiliza
   ( Felipe no quería el "se lo asigno a otro cristiano" del Excel).
8. **Emisor**: este año fijo **DIEGO ALBERTO FERNÁNDEZ FERNÁNDEZ** (CC 71.662.891),
   Bancolombia Ahorros 006-985327-51, **llave @diego2891 es de Bancolombia, NO Nequi**.
   Parametrizable por año. **GERMÁN TULIO FERNÁNDEZ FERNÁNDEZ es solo facturas** (GTFF-xxx),
   cuentas de cobro siempre Diego.
9. **Grupos familiares**: la cuenta compartida 26-005 (Osorio Arcila + Peña Santamaría) ES grupo
   familiar y **el pagador es Peña**. En la cuenta debe quedar especificado el valor de cada quien.
   Dentro de un grupo hay **subgrupos** → el sistema lo resuelve con grupos independientes + checkbox
   de **pagador** (a nombre de quién sale la cuenta).
10. **Pagos**: el cliente decide cómo pagar (transferencia, consignación, llave, otro banco);
    lo que se registra es **la forma en que pagó** (trazabilidad), la cuenta receptora es siempre
    la de Bancolombia.
11. **Autodescuento**: la cuenta sale **completa**; después el cliente se aplica el descuento → se
    registra como **ajuste** con motivo, y el pago real como pago. El año siguiente se arrastra el
    **valor de la cuenta de cobro** (NO el pagado); el pagado queda solo como referencia para
    renegociar (`PresupuestoCliente.valor_pagado_ref` está pensado para eso).
12. Formas de pago parametrizadas: `Transferencia|Consignación|Llave Bancolombia|Otro banco|Efectivo`.
13. **Facturas** (futuro): se emiten por DIAN; aquí solo se registrarían para consolidado y para
    asignar el número real GTFF-xxx.

## 4. Hallazgos de los datos (Excel guía)

Fuente: `Recursos/0-Presupuesto de cobros 2025 -FBZ.xlsx`, hoja principal **"Cuentas de Cobro"**.

- 183 clientes activos importados (personas naturales y jurídicas), columnas: No., Nombre, **Código** (único, 41,
  346, 370…), NIT, DV, valor a elaborar, cuenta No., medio envío, fecha envío, estado
  (PAGADO/PENDIENTE), forma de pago, fecha pago, 2 observaciones.
- Las cuentas del ciclo actual ya venían con estado y se importaron:
  - `26-001` Ochoa Velásquez Rafael — $470.000 PAGADA
  - `26-002` Ceballos Giraldo Catalina — $470.000 PAGADA
  - `26-003` Zapata Berruecos Beatriz Elena — $260.000 PAGADA (Banco Nu, obs en nota)
  - `26-004` González Moreno Elsy — **cuenta $410.000, autodescuento $30.000, pagó $380.000** (PAGADA con ajuste)
  - `26-005` Osorio Arcila $860.000 + Peña Santamaría $2.310.000 = $3.170.000 **ENVIADA** (8/09/2026)
- Parámetros leídos del Excel: IPC 5.1%, Mínima Mvto $230.000, Mínima 1ª vez $370.000.
  ⚠️ En el Excel las mínimas están en M3/N3 y el IPC en Q5 (hubo que ajustar columnas).
- Datos sucios normalizados al importar: "Tranferencia"→Transferencia, NITs sin formato, un No.
  duplicado (103), secciones TOTAL/RETIRADOS se saltan.
- Referencia histórica: los números `25-xxx` del ciclo anterior quedan en la nota del cliente
  ("C de C año anterior: 25-118").

## 5. Estado actual (lo que YA funciona, probado el 13-sep-2026)

- **Resumen/dashboard**: presupuestado vs emitido vs pagado vs saldo, lista de cuentas con estado
  y último envío, y **clientes sin cuenta de cobro** (pendientes de emitir).
- **Clientes**: alta/edición, activo/inactivo, grupo, presupuesto por año, historial completo.
- **Grupos familiares**: crear grupo, anclar/quitar miembros, marcar **pagador** (único por grupo).
- **Cuentas de cobro**: nueva (selector con filtro + "agregar grupo completo" + valores
  precargados editables), detalle con líneas por cliente (agregar/editar valor/anular/reactivar),
  fecha de la cuenta, **envíos** (medio+fecha+nota, permite reenvíos), **pagos y abonos parciales**
  (saldo automático, pasa a PAGADA sola al cubrir), **ajustes/descuentos** (autodescuento con
  motivo), **anular/reactivar** (número conservado), nota interna.
- **PDF**: diseño **VERTICAL aprobado por Felipe (15-sep)**: encabezado azul #1F4E79 con Nº + fecha,
  SEÑORES (pagador), DEBE A, POR CONCEPTO DE (label y concepto en líneas separadas), tabla con una
  fila por miembro (concepto propio opcional por línea, en letra pequeña bajo el nombre), SUBTOTAL →
  filas DESCUENTO → TOTAL si hay ajustes, **SON: valor en letras automático**, DATOS PARA EL PAGO
  (caja con alto corregido, la llave ya no sale cortada), OBS. si hay nota, firmas Atentamente/Aceptada.
  Verificado: 0 solapes, todo dentro de márgenes (bloques PyMuPDF). El PDF se sirve **inline**
  (modal en la app o pestaña nueva, ya no descarga ni saca al usuario).
- **Preview sin crear**: botón "Previsualizar PDF" en Nueva cuenta → POST `/cuentas/preview` genera
  el PDF en memoria (BytesIO) con los datos del formulario, **sin gastar número ni crear registro**.
- **Eliminar borrador**: en cuentas BORRADOR el botón de zona de peligro es **Eliminar** (borra la
  cuenta con sus líneas y **libera el número**: `numero_siguiente` retrocede si es el último usado).
  Enviadas/pagadas solo se anulan (número conservado). Ruta: POST `/cuentas/<cid>/eliminar`.
- **Pagador por cuenta**: campo `CuentaCobro.pagador_cliente_id` (override) + selector en detalle
  y en Nueva cuenta (nota: en `cuenta_nueva.html` el select `pagador_id` está DENTRO del form).
- **Parámetros**: emisor (nombre, CC, dirección, teléfonos, ciudad), datos bancarios multilínea,
  formas de pago, año gravable, prefijo, IPC, mínimas, concepto del PDF.
- **Años**: crear año nuevo con **arrastre automático** (prefijo = 2 últimos dígitos, mínimas ×IPC,
  concepto nuevo, datos del emisor heredados, presupuestos = último valor emitido ×IPC redondeado
  a centenas; si nunca se emitió usa el presupuesto). Activar/desactivar año.
- **Importador**: acumulativo y seguro de re-ejecutar (actualiza por código de cliente).
- Smoke tests: 17 rutas GET en 200, flujo completo crear→enviar→abono→pago→ajuste→anular verificado
  (anulada la 26-006 de prueba, la siguiente fue 26-007 → no reutiliza número; luego se limpió).
- Consecutivo actual: `numero_siguiente = 6`.

### Ronda 15-sep (tarde): acciones rápidas + Outlook + reglas de eliminación
- **Acciones rápidas**: panel en el detalle y menú ⚡ por fila en el listado; modales globales en
  `base.html` (`#mEnviar`, `#mPago`, `#mAjuste`, `#mAnular`, `#mOutlook`) que se rellenan con
  `data-accion/data-cid/data-numero/data-saldo/data-email` y cambian el `action` del form.
- **Reglas de vida de una cuenta**: sin envíos → botón **Eliminar** (borra todo y libera el número
  si era el último); con envíos → solo **Anular con motivo obligatorio** (`motivo_anulacion`, el
  número NO se reutiliza). Motivo mostrado en la zona de peligro si está anulada.
- **Redactar correo (Outlook)**: botón con modal de confirmación → POST `/cuentas/<cid>/outlook`:
  genera el PDF, lo guarda en la carpeta parametrizada (`Parametro.carpeta_pdfs_envio`, editable en
  Parámetros; defecto `Documentos\Cuentas de Cobro`), abre **Outlook clásico** por COM
  (`win32com`, pywin32 en requirements) en un hilo con `pythoncom.CoInitialize()`, con Para
  (email del pagador), asunto, cuerpo con detalle y **PDF adjunto**; NO envía solo (usa Display).
  Registra un Envio(medio=Correo, nota "Outlook") y pasa BORRADOR→ENVIADA. Confirmado que el PC
  tiene `Outlook.Application` COM registrado (también está el Outlook nuevo de Store, que NO sirve
  para COM: si algún día se desinstala el clásico, esta función deja de funcionar).
- **PDF en morado**: Felipe pidió el morado lindo PARA LOS PDF (la web ya era morada). Encabezado
  y cabecera de tabla ahora `#6D28D9`/`#4C1D95`; el azul #1F4E79 quedó solo como constante
  histórica sin uso.

### Ronda 15-sep (final): export Excel + importador de clientes + detalles
- **Nombre del PDF (v2, gusto de Felipe)**: `PAGADOR_CdeC_26_001.pdf`, ejemplo
  `OCHOA_VELASQUEZ_RAFAEL_CdeC_26_001.pdf` (pagador PRIMERO, luego CdeC y número). Aplica al
  visor y al guardado para Outlook.
- **Hilo de Outlook blindado**: el `except` usaba `current_app.logger` DENTRO del hilo →
  `RuntimeError: Working outside of application context` (así se perdió el error real). Ahora:
  captura el objeto app (`current_app._get_current_object()`), loguea con contexto y TAMBIÉN
  escribe `instance/logs/outlook.log` con traceback completo. Además intenta primero
  `GetActiveObject` (conectarse al Outlook ya abierto) y solo si no hay instancia viva usa
  `Dispatch` (lanzarlo). Diagnosticado en el PC: COM de Outlook registrado (Office16 clásico en
  `C:\Program Files\Microsoft Office\root`), pywin32 OK; el fallo `0x80080005 Server Execution
  Failure` del test se debió a que el agente corre ELEVADO y el Outlook del usuario estaba
  abierto (COM bloquea el puente entre niveles de integridad distintos). El servidor Flask
  corre normal → no debería pasarle; si vuelve a fallar, el log en `instance/logs/` dice por qué.
- **Exportar Excel** (`/exportar/excel`): botón en el Resumen. 4 hojas con cabecera morada:
  Resumen (totales), Cuentas (una fila por cliente/línea con saldo y pagador), Pagos (registro por
  pago), Clientes (183 con todo el contacto + presupuesto). openpyxl en memoria (BytesIO).
- **Importador de clientes** (`/clientes/plantilla` + POST `/clientes/importar`): plantilla xlsx
  descargable con 14 columnas (codigo, nombre, tipo, nit, dv, ciudad, direccion, telefonos, email,
  grupo, es_pagador, activo, nota, presupuesto). Código es la llave: actualiza si existe; crea solo
  si el selector `cliente_nuevo=SI`. Crea grupos que no existan y maneja pagador único por grupo.
  Pantalla Importar Excel ahora muestra ambas opciones lado a lado.
- **Correo visible**: columna Contacto en la lista de clientes (email + teléfono) y fila de
  "Contacto:" en la ficha (con aviso amarillo "sin correo" si falta — es el correo que usa Outlook).
- **Acciones rápidas en el Resumen**: botones pequeños por fila junto a Ver PDF (envío / pago /
  **descargar a carpeta** — pedido de Felipe: el tercer botoncito rojo con ícono ↓ era de ajuste y
  lo cambió por descarga directa; ajuste sigue en el detalle y en el menú ⚡ del listado).
  reutilizando los modales globales de `base.html`.

### Ronda 15-sep (cierre): Señor/Señora en el PDF según el pagador
- Quitado el rótulo "SEÑORES (PAGADOR)" del PDF. Ahora la etiqueta de la caja es el trato:
  **SEÑOR** / **SEÑORA** / **SEÑORES** (empresas).
- Nuevo campo `clientes.trato` ("" = automático, "SR", "SRA") con selector en el formulario del
  cliente; migración aplicada en ambas BD.
- `saludo_de_cliente()` en models.py deduce por el nombre de pila (formato APELLIDO APELLIDO
  Nombres): termina en A → Señora, en O → Señor (con excepciones femeninas: Consuelo, Rosario,
  Rocío, Amparo, Socorro, Milagros, Dolores), ambiguo (Rafael, iniciales, solo apellidos) →
  Señores neutro. El trato manual y el tipo PJ siempre ganan sobre la deducción.
- Cuando es Señores (empresa) la caja muestra "C. C. o NIT"; con Señor/Señora muestra además la
  ciudad. La fórmula "SRES." solo aparece para empresas.

### Ronda 15-sep (v2 correo): borrador .eml en vez de COM
- Felipe pidió cambiar el enfoque: en vez de abrir Outlook directo (COM fallaba con
  0x80080005 cuando había diferencia de elevación), **generar el borrador como archivo**.
- `/cuentas/<cid>/outlook` ahora genera en la carpeta parametrizada **dos archivos**:
  `PAGADOR_CdeC_XX_XXX.pdf` + `PAGADOR_CdeC_XX_XXX.eml`. El .eml lleva cabecera **X-Unsent: 1**
  (Outlook lo abre como BORRADOR EDITABLE, no como mensaje leído), To = correo del pagador,
  From = `Parametro.emisor_email` (campo nuevo en Parámetros, opcional), asunto, cuerpo con
  detalle y **PDF adjunto incrustado** (base64). Doble clic al .eml → se monta listo para enviar.
  Sin COM, sin pywin32, sin hilos: funciona aunque Outlook esté cerrado o abierto, y el error de
  elevación desapareció. pywin32 queda en requirements (no molesta) pero ya no se usa.
- Registro de Envio(medio=Correo) y BORRADOR→ENVIADA se mantienen igual.
- Probado: .eml válido (parse con email.parser: X-Unsent, To, From, Subject, cuerpo, 1 adjunto
  PDF con bytes %PDF), archivos con nombre pagador_CdeC, estado PAGADA intacto (solo BORRADOR
  pasa a ENVIADA), limpieza completa.

### Ronda 15-sep (v3): firma escaneada + descarga rápida + notas separadas
- **Firma en el PDF**: `Recursos/Firma.jpg` (218×100, subida por Felipe) se dibuja sobre la línea
  "Atentamente:" (ancho 95pt, alto proporcional ≈43.6pt). El bloque de firmas reserva el alto de
  la imagen (`fy = max(90, y-30-sig_h)`) y solo la dibuja si cabe sin invadir la caja superior;
  si no hay imagen o está corrupta, el PDF sale normal. Ruta resuelta relativa a la carpeta del
  proyecto (funciona en P:, Z: o donde se mueva).
- **Descarga rápida** (`POST /cuentas/<cid>/descargar`): guarda el PDF directamente en la carpeta
  de `carpeta_pdfs_envio` (sin diálogo). Botón "Descargar a carpeta" en el detalle y en el menú ⚡
  del listado (este por fetch JSON + alert con la ruta exacta).
- **Notas separadas** en `cuentas_cobro`: `nota` = NOTA INTERNA (nunca sale en el PDF) y
  `observaciones` = sección OBS. del PDF. Antes `nota` se volcaba al PDF como OBS. (confuso).
  Tarjeta de Notas en el detalle con los dos campos, campo observaciones en "Nueva cuenta" y en
  el preview. Migración aplicada en ambas BD.

### Ronda 19-sep: Clientes.xlsx sincronizado + scanner de rentas + buscador vivo + cuenta exprés
- **Sincronización del Clientes.xlsx (Recursos)**: 183 clientes cruzados POR NIT (fallback
  nombre), identidad (id/código/nit) quedó 100% fiel al respaldo 16-sep y a los códigos del
  Excel (verificado 183/183). Actualiza contacto, activo/inactivo (14), grupos G1–G25 (69
  clientes), pagadores (25 grupos con pagador único) y la columna nueva **C de C año anterior**
  (`clientes.cobrado_anterior`, 165 clientes, suma $110.040.000). Los presupuestos NO los toca
  el sync de fondo; los actualiza solo el importador de la pantalla Importar (que quedó
  lector de cabeceras: acepta el Clientes.xlsx de Felipe Y la plantilla del sistema).
  NOTA: los teléfonos/correos del Clientes.xlsx vienen vacíos (columnas sin datos); Felipe los
  llenará después (ver Contactos completos.xlsx como fuente).
- **Scanner de declaraciones** (`clientes.decl_renta`: vacío/NO_OBLIGADO/PRESENTADA): botón por
  fila en Clientes que cicla con 1 clic (fetch, sin recargar). `puede_cobrarse` = cliente
  presentada/no-obligado Y su grupo completo al día. Pestaña nueva **Cobrables**. En grupos.html
  badge "al día · cobrable" o "sin cobrar" (title nombra a los que faltan). NO hay botón masivo
  por diseño: Felipe marca presentadas cuando el DIAN las confirma.
- **Buscador vivo** en Clientes: filtra mientras se escribe, sin tildes (NFD), por nombre,
  código, NIT o grupo. Ya no se envía `q` al servidor.
- **Cuenta exprés** (`POST /clientes/<cid>/cuenta-expresa`): rayo por fila en Clientes. Crea
  cuenta BORRADOR con lo presupuestado del año activo (si el cliente es pagador de grupo:
  TODA la familia activa con presupuesto) y guarda el PDF directo en la carpeta de PDFs.
  Rechaza duplicados del año y clientes sin presupuesto.
- **Dos carpetas en Parámetros**: `carpeta_pdfs` (descargas y exprés; hereda el valor viejo de
  carpeta_pdfs_envio que quedó en la BD de Z: = `6-Presupuestos\Cuentas de Cobro`) y
  `carpeta_correos` (.eml; si está vacía usa la de PDFs). La clave vieja carpeta_pdfs_envio se
  migró a carpeta_pdfs en ambas BD.
- **Plantilla de importación** actualizada: ahora con Presupuesto y C de C año anterior.
- **Multi-PC (lo hecho por Felipe el 16-sep)**: venv fuera de OneDrive
  (`C:\EntornosPython\SistemaCobros-venv` por PC), `instalar_venv.bat` + `iniciar.bat` que lee
  la ruta desde `%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt`. NO sincronizar venvs; el
  código sincronizado aquí es compatible.
- **Lección dura**: la primera versión del sync cruzó por `codigo` y como Felipe renumeró
  clientes en su Excel, 84 filas quedaron con datos cruzados (nombres por NIT equivocado). Se
  reparó reconstruyendo desde `Respaldo codigo 2026-09-16/cobros.antes-fix-carpeta.db` y
  volviendo a sincronizar por NIT. REGLA: la identidad de un cliente es su NIT/código
  histórico; antes de cruzar dos fuentes, verificar que la llave coincida en AMBAS.

### Ronda 20-sep: correo formato oficina + trabajos adicionales + cobro desde grupos + contador autocurado + ruta maestro
- **Error reportado por Felipe (creación rápida)**: `UNIQUE constraint failed: cuentas_cobro.anio_cobro_id, cuentas_cobro.numero`.
  Causa: OneDrive sincroniza la BD entre PCs; el contador `numero_siguiente` quedó atrasado
  respecto a las cuentas que llegaron del otro PC. FIX: nuevo helper `_numero_libre(a)` que
  devuelve el primer consecutivo NO usado (autorepara el contador); usado en cuenta exprés,
  cuenta nueva y cuenta exprés de grupo. En Z: se ajustó el contador 10 -> 11.
- **Cuerpo del correo con formato de la oficina** (`_cuerpo_correo`): saludo personalizado con
  primer nombre (`_primer_nombre`, respeta trato; Señores => sin nombre), frase de adjunto
  singular/plural automática, bloque bancario COMPLETO desde `banco_info` (Bancolombia, cuenta,
  llave @diego2891, cédula), aviso notifica/notifican según plural, cierre de la casa. El modal
  de correo tiene textarea `correo_extra` para líneas adicionales (ej. "Adjunto declaración de
  renta presentada."). Asunto: "Declaración y Cuenta de cobro asesoría tributaria AG 2025 -
  Familia Peña Santamaría" (grupos G# usan apellidos del pagador) o "- Luis Fernando González".
- **Trabajos adicionales por cliente** (`TrabajoAdicional`): tarjeta nueva en el detalle del
  cliente con registrar (descripción + valor opcional), ciclo PENDIENTE/COBRADO con 1 clic y
  eliminar. Para el próximo año: revisar si se está cobrando bien. TABLA NUEVA: se crea sola
  con `db.create_all` (no requiere migración manual).
- **Cuenta exprés desde grupos** (`POST /grupos/<gid>/cuenta-expresa`): botón "cuenta del grupo"
  en el encabezado de cada grupo; valida que haya pagador, que ningún miembro activo esté en
  otra cuenta del año y que TODOS tengan presupuesto; crea la cuenta a nombre del pagador y
  deja el PDF en la carpeta.
- **Portabilidad OneDrive entre PCs (`_rebase`)**: si una ruta guardada (carpeta_pdfs,
  carpeta_correos, ruta_maestro) no existe en este PC pero pasa por `...\OneDrive\...`, se
  reconstruye con la raíz local de OneDrive (env OneDrive/OneDriveConsumer/~OneDrive) SI el
  destino existe; si no existe equivalente, se conserva la original. Felipe pidió "nada
  hardcodeado": rutas absolutas guardadas funcionan en casa (Z:) y oficina (C:).
- **Integración Sistema Maestro**: su BD (`sistema_maestro_v4.db`, tabla `obligaciones`) ya
  tiene 148 rentas AG-2025 con `scanner_estado='PRESENTADA'` y cruce por NIT 170/183. Nuevo
  parámetro `ruta_maestro` (carpeta hasta sistema-maestro-v7) + botón "Rentas del maestro" en
  Clientes (sync global, marcó 78 clientes en prueba) + ruta por cliente
  `/clientes/<cid>/decl-maestro` (marca al cliente o a todo su grupo). MAESTRO ES SOLO LECTURA.
  La columna decl_renta sigue siendo editable a mano (_fuente de la verdad_ para cobrar).
- Tests: `probar_ronda8.py`, `probar_rebase.py` nuevos; `probar_ronda7/ronda6/eml` actualizados
  para usar carpetas de prueba en `%TEMP%` (fuera de OneDrive: `_rebase` no las redirige).
  `generar_desde_dict` ahora crea la carpeta destino si no existe.
- **DECISIÓN de Felipe (19-sep)**: la fase 2 del maestro NO se hace por ahora ("dejemos la cosa
  quieta"). La integración actual (rentas presentadas) queda como está. Lo de otros impuestos/
  presupuesto de PJ irá con **factura electrónica real (DIAN)**, que todavía no está organizada.
  La lectura de estados del maestro queda solo como apoyo del flujo de rentas PN/familias.

### Ronda 19-sep (2): toggle CASA/OFICINA para la ruta del maestro (igual al Maestro)
- Felipe pidió el mecanismo que ya usa el Sistema Maestro: rutas por PC (`ruta_casa`,
  `ruta_oficina` en Parámetros; la primera vez se llenan las dos) + toggle de 1 clic
  (`POST /parametros/ubicacion`) que activa la ruta de la ubicación actual.
- **La ubicación activa NO vive en la BD** (la BD viaja por OneDrive y llegaría la del otro PC):
  vive en `%LOCALAPPDATA%\SistemaCobros\ubicacion.txt` (misma idea que el venv fuera de
  OneDrive). Primera vez se AUTODETECTA (gana la ruta guardada que exista en el PC; si no, letra
  Z:=CASA, C:=OFICINA) y cada PC se queda acordando de su lado.
- `_ruta_maestro_activa()` = ruta de la ubicación activa pasada por `_rebase` (si el PC tiene
  otra letra, se adapta igual). Los dos syncs del maestro usan la activa; si en la ubicación
  activa no hay ruta, avisan en vez de fallar.
- **POST /parametros ahora es a prueba de posts parciales**: solo actualiza los campos que
  vienen en el formulario (antes un POST sin un campo BORRABA su valor; lo destapó un test
  dejando banco_info vacío en P:; Z: estaba sano; P: restaurado copiando de Z:).
- En Z: quedaron precargadas ruta_casa (Z:...maestro-v7), ruta_oficina (C:\Users\Usuario\...)
  y ruta_maestro. En P: igual + ubicacion.txt = CASA.
- Tests: `probar_toggle.py` nuevo (7 asertos, incl. aviso sin ruta y rebase de la ruta del otro
  PC). Suite completa verde (7 archivos).

### Ronda 20-sep: botón de descarga rápida de correo desde Clientes
- Felipe pidió un botón rápido para bajar el último mensaje guardado en la carpeta de correos,
  junto al de descarga rápida de PDF en la pantalla Clientes.
- **Botón ✉ (envelope-open, verde)** en cada fila de Clientes, junto al rayo exprés: solo
  aparece si hay .eml de ese cliente en la carpeta de correos. Los .eml se nombran
  SLUG-DEL-PAGADOR_CdeC_26_XXX.eml, así que: si el cliente es pagador de grupo, el botón
  aparece con correos de cualquier miembro y el title lo indica ("baja el más reciente").
- `GET /clientes/<cid>/correo` → baja el .eml MÁS RECIENTE (mtime) del pagador. Sin correos:
  flash claro y sin romper. El listado precalcula `correos[cli_id] = n` leyendo UNA vez la
  carpeta (nada de I/O por fila).
- Lección de código: `ultimo_envio`/`pagador_principal` son de CuentaCobro, NO de Cliente; una
  edición apurada los pegó en la clase equivocada y Flask tiró AttributeError. Verificar DÓNDE
  termina cada clase antes de añadir properties.
- Lección de tests: las URLs de Flask no contienen el nombre del endpoint (usar el path
  `/correo"` para aserciones). Y `send_file` mantiene el archivo abierto un momento: en tests
  usar try/PermissionError al borrar.
- Tests: `probar_boton_correo.py` (5 asertos). Suite completa: 8 archivos TODO OK.
  Sincronizado a Z: (banco_info y carpeta_correos de Z: intactos).
- Ajuste tras prueba de Felipe: el botón de correo era invisible con la carpeta vacía y no
  se entendía. Ahora el sobre está SIEMPRE visible: verde abierto (envelope-open) con
  correos, gris cerrado (envelope) sin ellos. ParaEnviar estaba vacía (0 .eml) — por eso
  no veía nada; no hacía falta ningún parche manual, el código ya estaba en Z:.
- Clarificación con caso ARBELÁEZ COCK GABRIEL JAIME: el botón ✉ baja MENSAJES .eml
  generados (borradores), no el correo de contacto. Gabriel no tiene cuentas este año
  (0 como pagador, sin grupo) pero su ficha SÍ tiene email (g.arbelaez.cock@gmail.com).
  El aviso ahora distingue: con email de contacto sugiere generar la cuenta y muestra el
  contacto; sin email tampoco, lo dice explícito.

### Ronda 20-sep (b): EXPRESO COMPLETO — 1 clic = cuenta + PDF + borrador .eml
- Felipe: "la opción 1 es la que siempre quice": el rayo ⚡ ahora hace el flujo entero.
- `_generar_eml(cuenta, carpeta, extra)` extraído de cuenta_outlook (que ahora lo usa):
  genera PDF + .eml X-Unsent con To/Subject/cuerpo de oficina/adjunto. Devuelve ruta o None
  si el pagador no tiene email.
- cliente_cuenta_expresa y grupo_cuenta_expresa: tras crear cuenta+PDF, si el pagador tiene
  correo → generan .eml en carpeta de correos, registran Envio, estado queda ENVIADA, y el
  flash lo dice. Sin email del pagador → solo PDF (cuenta queda BORRADOR) con aviso claro.
- Confirmaciones en clientes.html y grupos.html actualizadas (avisan que genera .eml).
- El sobre ✉ del listado queda verde tras el expreso: descarga del borrador al instante.
- Lección de tests (otra vez, ahora documentada): carpetas a temporales ANTES del clic —
  la primera corrida escribió PDF/.eml en las carpetas REALES de Z: (borrados luego; la BD
  de Z: nunca se tocó porque el test usa la de P:). El orden de restauración en baterías:
  reset_estado AL FINAL de cada suite y restaurar_params desde la raíz del workspace.
- Tests: `probar_expreso_completo.py` (Gabriel real: cuenta 26-006, ENVIADA, .eml con
  X-Unsent y destinatario correcto, sobre verde). Batería 9/9 TODO OK; P: verificada
  (número 6, presupuesto 360000 intacto, 9 envíos, params Z:).
- Refinamiento tras prueba real de Felipe: el rayo sobre cliente con cuenta BORRADOR
  previa (Gabriel 26-012 creada con el código viejo sin reiniciar) ahora la COMPLETA:
  genera PDF + .eml, registra Envio y la pasa a ENVIADA. Si ya tiene .eml, el aviso
  sugiere el sobre ✉. Test `probar_completar_borrador.py` (cuenta 900 temporal, TODO OK).
- Importante para Felipe: los cambios del sistema requieren CERRAR Y ABRIR INICIAR.bat —
  el programa corre desde Z: y los archivos se sincronizan luego; un programa abierto
  sigue con el código de cuando arrancó.

### Ronda 20-sep (c): el sobre ✉ de Clientes = MISMA función que Redactar correo
- Felipe dejó claro el pedido original: "el botón redactar correo de la cuenta, pero desde
  Clientes, sin entrar a cada cuenta". Nada de descargador de archivos viejos.
- `cliente_correo` reescrito: toma la cuenta vigente del cliente (más reciente no anulada
  con línea ACTIVA), ejecuta `_generar_eml` (MISMO helper del botón de la cuenta) y DESCARGA
  el .eml al navegador (también queda en ParaEnviar). Registra Envio solo la primera vez
  (clics repetidos no duplican), pasa BORRADOR→ENVIADA igual que Redactar correo.
- Avisos: sin cuenta por cobrar → "primero genera la cuenta (rayo ⚡)"; pagador sin email →
  "regístrelo en su ficha".
- Acuerdo de trabajo con Felipe: pedidos con dos lecturas posibles → confirmar en 2 líneas
  la interpretación ANTES de escribir código. El descargador de .eml viejos fue mi mala
  lectura; no repetirla.
- Tests: `probar_boton_correo.py` reescrito (5 casos: sin cuenta, descarga Gabriel, ENVIADA
  + Envio, segundo clic sin duplicar, sin email). Batería 10/10 TODO OK. P: verificada
  (numero_siguiente 6, sin cuentas 900 residuales, params Z:).

### Ronda 20-sep (d): nombres de PDF en formato nombre propio
- Felipe pidió: PDF con mayúscula inicial en nombres y apellidos, no TODO MAYÚSCULA.
- `_nombre_propio(s)` nueva: capitalize por palabra con partículas en minúscula (de, del,
  la, y...) salvo al inicio: "HERNÁNDEZ DE COCK BEATRIZ" → "Hernández de Cock Beatriz".
  `_nombre_pdf` ahora hace `_slug_archivo(_nombre_propio(...))`:
  Ochoa_Velasquez_Rafael_CdeC_26_001.pdf en vez de OCHOA_VELASQUEZ_... .
- Las tildes se quitan igual que siempre (solo acentos; la mayúscula inicial queda).
- Seguro por diseño: la vista /cuentas/<cid>/pdf REGENERA el PDF al vuelo (nada busca
  archivos viejos por nombre), y los .eml salen del mismo _nombre_pdf. Archivos viejos en
  disco no cambian de nombre (solo los nuevos).
- Tests: `probar_nombre_propio.py` (7 nombres + 2 cuentas reales + partículas). Tests viejos
  actualizados de OCHOA→Ochoa (probar_eml.py, probar_ronda6.py). Batería 11/11 TODO OK.

### Ronda 21-sep: marcas de pago en Clientes + imagen PNG para WhatsApp
- Felipe pidió: (1) ver en Clientes quién ya tiene cuenta enviada y quién ya pagó;
  (2) menú de acciones de Cuentas con "Generar imagen (WhatsApp)" y su carpeta en Parámetros.
- **Marcas de estado**: `clientes()` calcula `estados_cobro[cli_id]` (pagada > enviada >
  cobrada) según las cuentas del año con línea ACTIVA del cliente. En clientes.html el
  nombre queda en verde `a.cobro-pagada` + check ✓ (bi-check-circle-fill) si PAGADA, en
  ámbar `a.cobro-enviada` + avión ✈ (bi-send-fill) si ENVIADA; tooltips explican.
- **Imagen PNG**: `app/imagen_cuenta.py` con `generar_imagen(cuenta, ruta)`: rasteriza el
  PDF real a 150 dpi con pymupdf (importar `pymupdf`, `fitz` deprecado); fallback Pillow
  dibuja lámina vertical (banda morada, clientes, concepto, total destacado, banco, firma).
  NO reemplaza el PDF: es lámina para compartir. Ruta `POST /cuentas/<cid>/imagen` (JSON
  para el menú, guarda en `_carpeta_imagenes()` y avisa la ruta; PNG también descargable
  por navegador si se llama sin Accept JSON).
- `_carpeta_imagenes()` = param `carpeta_imagenes` (vacía = carpeta de PDFs), con _rebase.
  Aceptado en POST /parametros parcial. Campo nuevo en parametros.html.
- Menú de acciones: item "Generar imagen (WhatsApp)" con JS en base.html (deshabilita el
  botón mientras genera; avisa ruta final).
- requirements.txt: + Pillow, + pymupdf.
- Tests: `probar_ronda_imagenes.py` (8 asertos: clases por estado, íconos, PNG
  Arbelaez_Cock_Gabriel_Jaime_CdeC_26_901.png 1275x1650, params parcial seguro, menú).
  Batería 12/12 TODO OK (ronda8 corregido: faltaba commit al reasignar pagador de prueba;
  lección: el test-instrumentado mostró que el POST usaba pagador viejo por rollback del
  contexto).

### Ronda 21-sep: hoja Maestro en el export + deshacer envío
- Felipe pidió: (1) hoja adicional en el Excel exportado con los datos del maestro clásico
  (captura: No., nombres, código, NIT, DV, valor, cuenta No., ENVIADA, fecha envío, estado
  del cobro, medio de pago, fecha de pago, observaciones); (2) revertir un "envío" marcado
  por error: le dio "descargar correo" (✉) a un cliente al que aún no le había hecho la
  declaración, y al descargar el .eml la cuenta quedó ENVIADA.
- **Hoja Maestro** (5ª hoja del export): una fila por cliente con línea ACTIVA en cuentas
  del año (los sin cuenta NO aparecen, como en el Excel clásico). Columnas: No., Nombre,
  Código, NIT formateado, DV, Valor de su línea, Cuenta No., ENVIADA (Sí/“), Fecha envío
  (del último Envio), Estado del cobro (PAGADO si saldo≤0; ENVIADA si hay envíos/estado;
  PENDIENTE si borrador; ANULADA), Medio de pago (del último envío, o forma del último
  Pago), Fecha de pago (último Pago), Observaciones (de la cuenta, máx 80), Pagado, Saldo.
  OJO: columna CÓDIGO es el código histórico del cliente (NO el id interno; el test lo
  confundió una vez: pagador cta5 = id 41 = código 349 DÍEZ, no ACEVEDO).
- **Deshacer envío**: `POST /cuentas/<cid>/envio/<eid>/eliminar` (envio_eliminar): borra el
  registro Envio y llama cuenta.marcar_estado() → sin envíos y con saldo vuelve a
  BORRADOR (si ya estaba PAGADA no baja). Envío inexistente/ajeno → flash, no 404.
  Botón ✕ junto a cada envío en la ficha (cuenta_detalle.html, sección Envíos) con
  confirmación: "La cuenta vuelve a BORRADOR (sirve para deshacer un envío marcado por
  error)". El .eml/PDF ya descargados siguen en disco (no molestan: son solo archivos).
- Tests: `probar_maestro_deshacer.py` (12 asertos: hojas del libro, cabeceras, PAGADO de
  Ochoa con fecha, Gabriel sin cuenta no aparece, ENVIADA del pagador cta5, ciclo
  enviar→deshacer→BORRADOR, envío ajeno). Batería 13/13 TODO OK. Verificado en vivo:
  export 200 con 5 hojas, ficha de cuenta con botón ✕ funcional.
- **BUG HTML corregido (formularios anidados en parametros.html)**: el form del toggle
  CASA/OFICINA estaba DENTRO del form grande de parámetros; los navegadores no anidan
  forms: el `</form>` interno cerraba el grande antes de tiempo y el botón "Guardar
  parámetros" quedaba fuera → no guardaba NADA (Felipe: "no me deja guardar el parámetro
  de la carpeta de imágenes"). Arreglo: form grande con id=fparams; botón del toggle con
  atributo `form="fubic"` apuntando a un form oculto independiente al final de la página
  (HTML5). `probar_params_fix.py` verifica: sin `</form>` dentro del form grande, POST de
  carpeta_imagenes guarda y se vuelve a mostrar. También explicación del "no veía nada":
  el sistema no estaba (re)iniciado tras la actualización + faltaban pymupdf/Pillow en el
  venv local del PC (instalados a mano: `python -m pip install pymupdf Pillow`).
- **Hoja Maestro con TODOS los clientes (pedido de Felipe 21-sep)**: la otra persona debe
  ver el presupuesto completo del año y él va actualizando el estado de cobro. Ahora la
  hoja lista TODOS los clientes activos (169 en la BD real): sin cuenta → presupuesto en
  columna Valor y lo demás en blanco; con cuenta → igual que antes. Verificado en vivo:
  169 filas = 169 activos, 22 con cuenta, 147 sin cuenta (145 con presupuesto > 0).
  Test actualizado: Gabriel ARBELÁEZ aparece una vez con 360000 y sin estado; ojo con
  nombres repetidos en la lista (varios GABRIEL/OCHOA): el test apunta al nombre completo.

### Bug corregido
- 13-sep: los labels monetarios usaban `${"{:,.0f}".format(x)}` (JS) en vez de Jinja → se veía la
  fórmula cruda. Se creó el **filtro Jinja `|money`** en `app/__init__.py` y se reemplazaron los 31
  usos en 7 plantillas. Quedó sincronizado en Z: y P:. Los `${...}` de `cuenta_nueva.html` son JS
  legítimo (selector de líneas), no tocar.

## 6. Arquitectura (para tocar código)

**Tema visual (15-sep)**: morado sobrio definido en `base.html` con variables CSS
(`--morado: #6d28d9`, `--morado-osc`, `--morado-claro`, `--morado-med`); navbar con degradado
morado; botones/links/focus/checkbox sobreeescritos. El PDF mantiene su azul #1F4E79 (así lo
aprobó Felipe: interfaz morada, documento azul).

**Modal PDF global**: `base.html` trae `#modalPdf` (iframe modal-xl) + delegación global de clics:
cualquier elemento con `data-pdf="<url>"` abre el PDF en el modal; con `data-pdf-form="#idForm"`
hace POST del formulario por fetch y muestra el blob (usado por Previsualizar). Botón "Pestaña
nueva" dentro del modal. No usar `<a target=_blank>` directo para PDFs salvo que se quiera fuera
del modal.

```
app/
├── __init__.py       create_app() + filtro money (formato $ 1.234.567)
├── models.py         Parametro(clave/valor), AnioCobro, GrupoFamiliar, Cliente,
│                     PresupuestoCliente(año+valor), CuentaCobro(estado, líneas, saldo),
│                     CuentaLinea, Envio, Ajuste, Pago. Estados: BORRADOR|ENVIADA|PAGADA|ANULADA
├── routes.py         Blueprint "main": dashboard, clientes, grupos, cuentas, pagos, ajustes,
│                     envíos, PDF, anular, parámetros, años, importar, api_valor_cliente
├── importar.py       leer_filas_clientes(), leer_parametros(), importar() → acumulativo
├── pdf_generator.py  generar_pdf(cuenta, ruta) con ReportLab; ruta_pdf() estandariza carpeta
└── templates/        base + 10 pantallas, Bootstrap 5 (CDN), badges por estado
```

- Reglas en el modelo: `CuentaCobro.marcar_estado()` recalcula (salvo ANULADA); `saldo = total −
  ajustes − pagado`; `pagador_principal` = cliente con `es_pagador` o primera línea;
  `numero_formateado` = `{prefijo}-{numero:03d}`.
- El pagador se hace único en el grupo al guardar (routes lo fuerza con UPDATE).

## 7. Pendientes / siguientes pasos

**Fase 2 (acordada, sin fecha):**
- [ ] Valor en letras en el PDF (el formato viejo lo traía)
- [ ] Exporte consolidado a Excel (estilo hoja "Consolidado Cobros")
- [ ] Búsqueda global
- [ ] Usar `PresupuestoCliente.valor_pagado_ref` para guardar el pago real del año como referencia
  de negociación (hoy el arrastre usa el valor de cuenta, que es lo acordado)

**Fase 3 (diseño listo, no empezar sin Felipe):**
- [ ] Registro de facturas DIAN GTFF-xxx (solo registro, para consolidado y saber cuántas faltan
  por montar en la DIAN) — hereda estructura de cuentas: documento + líneas + estados
- [ ] Vencimientos de declaraciones (hoja "Vencimientos Pnas Nat AG")
- [ ] Cálculo automático de retención en la fuente por grupo pagador (base acumulada, UVT, 11%)

**Ideas sueltas mencionadas:**
- Que la creación de cuenta desde grupo sugiera el pagador como cabeza automáticamente (hoy se
  agrega el grupo completo y el PDF usa el pagador como "SEÑORES").
- Depurar catálogo de medios de envío (Correo, WhatsApp, Correo y WhatsApp, Físico, Otro).

## 8. Notas de entorno (oficina)

- Rutas largas con espacios y acentos: en PowerShell usar `-LiteralPath` y comillas.
- `python` del PATH puede ser `Z:\AutoClaw\resources\python\python.exe` (sin venv) → usar
  `C:\Python313\python.exe` o `py -3.13`.
- Puertos ocupados por otros sistemas del usuario: 5000 (Maestro), 5678 (contraseñas),
  5173 (Don Peppini Contadore). Este sistema: **5001**.
- La primera vez en la oficina: correr `INICIAR.bat` (crea `venv` e instala dependencias solo).
