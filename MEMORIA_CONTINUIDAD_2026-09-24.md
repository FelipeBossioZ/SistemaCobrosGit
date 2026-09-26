# MEMORIA DE CONTINUIDAD — Sistema de Cobros
**Fecha:** jueves 24/09/2026, 15:30 · **Hecha por:** Sistema de Cobros (agente) a petición de Felipe
**Propósito:** continuar el BIG UPDATE en el otro PC. Este documento es autocontenido: no necesitas el chat anterior.

---

## 0. DÓNDE ESTOY Y CÓMO ARRANCAR

| Cosa | Ruta / comando |
|---|---|
| **Producción (puerto 5001)** | `...\6-Presupuestos\Sistema de Cobros` → `iniciar.bat` |
| **Pruebas (puerto 777)** | `...\6-Presupuestos\SistemaPruebas` → `iniciar_pruebas.bat` |
| **Venv Python** | `C:\EntornosPython\SistemaCobros-venv` (NO está dentro de OneDrive; si el otro PC no lo tiene, ejecutar `instalar_venv.bat`) |
| **Respaldos de código** | `Respaldo codigo 2026-09-24` en ambas carpetas (sufijos `.antes-faseA.bak`, `.antes-morosos.bak`, `.antes-pagotodo.bak`, `.antes-faseB.bak`, `.antes-cierremoroso.bak`) |
| **Maestro (SOLO LECTURA)** | `...\1- PLANIFICACIÓN OFICINA\2026\Sistema maestro\sistema-maestro-v7\data\sistema_maestro_v4.db` |
| **Excel 2025 (cobros año anterior)** | `...\6-Presupuestos\0-Presupuesto de cobros 2025 -FBZ.xlsx` hoja 'Cuentas de Cobro' |
| **App Flask** | `app/` con `models.py`, `routes.py`, `migraciones.py`, `cobros_2025.py`, `asesorias_seed.py` (solo 777), `templates/` |

**Reglas de oro (acordadas con Felipe, NO negociables):**
1. Producción congelada salvo aprobación explícita; se desarrolla SIEMPRE primero en el 777.
2. A producción solo va CÓDIGO. La BD de producción solo recibe columnas/tablas nuevas vía `migraciones.py` (idempotente). Los datos los importa Felipe con botones.
3. La BD del 777 nunca viaja a producción. El maestro se lee SOLO lectura.
4. Todo parche: respaldo primero, anclas con count==1 verificadas antes de escribir, probar con test script, y recién entonces pasar a producción.
5. El formato del PDF de la cuenta de cobro NO cambia.
6. Correos: solo llenar celdas vacías, email principal, vacío si hay duda.
7. PowerShell manglea `python -c` con comillas anidadas → escribir scripts a `.openclaw/tmp/*.py` y ejecutarlos.
8. `url_for` nunca en HTML final renderizado; `db` se importa de `app.models`; `cuenta.lineas` es lista (no query).

---

## 1. ESTADO REAL DEL SISTEMA AL CIERRE DE HOY

### En PRODUCCIÓN (5001) — funcionando y verificado
- **Fase A completa:** dashboard "FALTA POR COBRAR", listado con 4 columnas (Presupuesto 2026 | Pagado 2026 | Cobrado 2025 | Efect. pagado 2025), importador de Excel 2025 (botón "Pagos 2025 (Excel)" — **Felipe aún no lo ha ejecutado en producción**, los valores 2025 están en cero ahí; o los importa o los llena a mano con el editor por clic).
- **Módulo Morosos:** deudores (cobrado 2025 > pagado), "sin cobro registrado 2025" (caso Afanador), notas automáticas, "✓ pagó todo" (un clic marca pagado = cobrado, actualiza totales sin recargar), **cierre "no es moroso"** con nota OBLIGATORIA (acuerdos internos), tabla "Acuerdos internos / descontados" con botón "↩ reabrir", tarjeta DESCONTADO, y **hoja 6 "Morosos y acuerdos" en el Excel exportable** (`/exportar/excel`, con nota y valor descontado por cliente + totales).
- Pendientes manuales de Felipe en producción: borrar cuenta duplicada **26-013** (Gustavo, BORRADOR sin envíos) y pulsar "Sincronizar grupo" en **26-022** (Flury).

### SOLO en el 777 — Fase B (asesorías), falta revisión de Felipe
- Catálogo `AsesoriaCatalogo` con 16 estándares sembrados (`app/asesorias_seed.py`): Renta 100%, IP 50%, Exógena 75%, Exógena Mpio 15%, F2516 10%, Activos Exterior 30%, Cámara 50%, IVA base $150.000, RF base $100.000, Devoluciones 20%, FE inscripción $80.000, FE factura $20.000, Contabilidad PN 1 SMLV/mes (sin valor: SMLV 2026 sin decreto al 24/09), PJ básica $600.000/mes, PJ compleja 1 SMLV/mes, Otras libre.
- `AsesoriaCliente` (cliente × asesoría: incluir, % o valor; None = usa estándar).
- Ficha de cliente: card "Asesorías 2026" (checkbox, % editable sobre estándar, subtotales, total, diferencia vs presupuesto). Guardado por fetch sin recargar.
- Parámetros → enlace "Catálogo de asesorías" (`/asesorias`, edición inline).
- Rutas: `GET/POST /asesorias`, `POST /clientes/<cid>/asesorias`.
- Tests T1–T10 OK. Datos de prueba limpiados. **NO pasada a producción** (espera OK de Felipe).
- Convención clave: los % van en la MISMA unidad que el presupuesto (Renta 100 ≈ presupuesto completo del año del cliente).
- En el 777 quedó un ejemplo vivo: CALLE ARANGO CARLOS ENRIQUE con cierre de moroso (350.000/330.000, "Acuerdo interno").

### Sin iniciar
- **Fase C:** estados por asesoría leyendo el maestro (NIT cross → obligaciones: RENTA_PN/PJ, ACTIVOS_EXTERIOR, EXOGENA, EXG_MED, PATRIMONIO, FORMATO_2516, IVA, RETEFUENTE, REGISTRO_MERCANTIL, ICA, RUB, RST, CONSUMO, SUPERSOCIEDADES, ANTICIPO_RST). Reglas de Felipe: RUB 15%, SUPERSOC 75%, CONSUMO/ANTICIPO_RST toman base de Retefuente, RST(SIMPLE) se trata como renta, 2516 default 10% (él cambia a 20% a mano), cantidades desde el maestro, devoluciones/FE/contabilidad manuales por cliente.
- **Fase D:** sincronizar Excel de clientes (activos/inactivos/nuevos) + control estructurado para no repetir el caso Afanador.

---

## 2. LOS 6 PUNTOS NUEVOS DE FELIPE (24/09 15:30) — PLAN PROPUESTO

> Transcripción fiel + propuesta técnica de cada uno. Ninguno está implementado todavía.

### Punto 1 — "Photo card" por cliente (desglose de lo cobrado)
**Pedido:** por cada cliente, generar una "photo card" o algo parecido que discrimine TODO lo que se le está cobrando, por si el cliente la pide.
**Propuesta:** ruta `/clientes/<cid>/photo-card` con plantilla imprimible (mismo estilo morado del sistema, botón imprimir/PDF del navegador): datos del cliente, paquete de asesorías del año con % y subtotales, total vs presupuesto, estados de presentación (cuando exista Fase C). Enlazarla desde la ficha y desde la nota interna de las cuentas (ver punto 5).

### Punto 2 — IVA y recorrido masivo con el maestro
**Pedido:** "no me calcula los IVAs" y que el sistema recorra todos los clientes marcando qué se le hizo y en qué cantidades.
**Diagnóstico:** los ítems de tarifa fija (IVA base $150.000, RF base $100.000, contabilidad SMLV) hoy no tienen campo de CANTIDAD, así que no puede haber cantidad × tarifa. Además nada lee aún el maestro por cliente.
**Propuesta:** (a) agregar `cantidad` a `AsesoriaCliente` (default 1) para ítems de tarifa fija; subtotal = cantidad × tarifa; (b) botón "Depurar con maestro" (masivo y por cliente) que lea el maestro (obligaciones por NIT: impuesto, periodo, estado, scanner_estado) y prellene inclusiones + cantidades (ej: 12 meses de IVA presentados = 12 × tarifa). Conexión natural con la Fase C ya planificada.

### Punto 3 — Advertencia y documentación al mover el presupuesto
**Pedido:** si descubro que me faltó cobrar algo (ej: activos en el exterior) y el total se mueve del presupuesto inicial, el sistema debe advertirme (por exceso PERO también por defecto, no quiero cobrar de más ni de menos) y TODO debe quedar documentado.
**Propuesta:** (a) aviso visible en la ficha cuando total del paquete ≠ presupuesto (con % de desvío, verde/amarillo/rojo); (b) tabla `presupuesto_historial` (cliente, año, valor anterior, valor nuevo, motivo OBLIGATORIO, fecha) — la auditoría queda en la ficha y en el Excel; (c) regla de PDFs: si la cuenta está en BORRADOR → se regenera con el valor nuevo; si está ENVIADA o PAGADA → NO tocar el PDF, dejar nota interna en la cuenta: "Error en el cálculo de la cuenta. Valor real $X. Ver photo card en cliente".

### Punto 4 — Código automático para clientes nuevos
**Pedido:** el sistema debe asignar el código solo, tomando el último número.
**Propuesta:** en el formulario de cliente nuevo, precargar `max(código)+1` (editable por si acaso) y validar unicidad al guardar.

### Punto 5 — Total en tiempo real + depurado automático estándar + flujo con PDF
**Pedido:** el label "Total asesorías 2026 / diferencia vs presupuesto" no se actualiza en tiempo real; quiere que muestre cuánto FALTA (amarillo), si se PASA (rojo) o OK (verde) mientras revisa y edita valores. Además: que el sistema haga el recorrido con el maestro y arroje un PRIMER desglose automático según los estándares cuando la renta esté PRESENTADA (cliente listo para cobrar); él lo confirma o modifica; y si eso afecta el presupuesto inicial, aplicar la regla del punto 3 (PDF se marca / nota interna si ya fue enviada o pagada).
**Propuesta:** (a) arreglar el JS: hoy el fetch actualiza el total pero NO el label de diferencia (`ases-dif` estático) → recalcular diferencia en vivo con umbrales de color (tolerancia sugerida: ±$1.000); (b) botón "Depurar con maestro" (punto 2) que solo propone el desglose estándar para clientes con renta PRESENTADA/grupo al día, queda en "propuesto" hasta que Felipe confirme; (c) al confirmar, si el total ≠ presupuesto → registrar en historial (punto 3) y aplicar la regla de PDF/nota.

### Punto 6 — Esta memoria
Hecho: este documento está en la raíz de `SistemaPruebas` (viaja por OneDrive al otro PC). Copia de trabajo también en la memoria del agente.

**Orden sugerido para retomar:** 4 (código automático, es trivial) → 5a (total en vivo con colores) → 1 (photo card) → 2 (cantidades + lectura maestro) → 3 (historial presupuesto + regla PDF/nota) → 5b (depurado automático) → Fase D. Todo primero en el 777, con tests, y a producción solo con OK de Felipe.

---

## 3. CHECKLIST DE ARRANQUE EN EL OTRO PC

- [ ] Esperar a que OneDrive termine de sincronizar `6-Presupuestos` (verificar que este archivo exista allá).
- [ ] Si no existe el venv: crear con `instalar_venv.bat` (Python 3.14, dependencias Flask/openpyxl). Recordar: el venv vive en `C:\EntornosPython`, fuera de OneDrive.
- [ ] Levantar el 777 (`iniciar_pruebas.bat`) y revisar la **Fase B**: ficha de un cliente (card Asesorías 2026) y Parámetros → Catálogo de asesorías.
- [ ] Si la Fase B cuadra → pasar a producción (mismo mecanismo: copiar `models.py`, `migraciones.py`, `asesorias_seed.py`, `__init__.py`, `routes.py`, `templates/cliente_detalle.html`, `templates/parametros.html`, `templates/base.html`, `templates/asesorias_catalogo.html`; respaldos previos; NUNCA copiar la BD del 777).
- [ ] Ejecutar los puntos 1–5 de este documento en el 777.
- [ ] No olvidar en producción: borrar 26-013 y "Sincronizar grupo" en 26-022.
- [ ] SMLV 2026: cuando salga el decreto, poner el valor en el catálogo (Contabilidad PN y PJ compleja).

*Documento creado el 24/09/2026 a las 15:30. Sistema verificado funcionando: producción 5001 y pruebas 777.*
