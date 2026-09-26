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

## 2. GIT LOCAL (nuevo)
- **777**: repositorio con commit inicial `Estado inicial pruebas 777...` + commit `Etapa 0...`. Hacer commit despues de cada sesion:
  `git -C "Z:\OneDrive\OFICINA\FELIPE\Oficina Felipe\6-Presupuestos\SistemaPruebas" add -A`
  `git -C "..." commit -m "descripcion del cambio"`
- **Produccion**: repo inicializado y TODO STAGED (index = estado actual). Sin commits todavia, por decision de Felipe.
- `.gitignore` en ambos: excluye `instance/`, `__pycache__/`, `Respaldos BD/`, `Respaldo codigo */`, `salidas/`.
- El .git viaja por OneDrive (es chico, solo texto). No interfere con la sync.

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

## 5. PREGUNTAS ABIERTAS (las respuestas llegan por chat)
Q1 renta base: ¿guardar al confirmar (recomendado, auditable) o derivar en vivo?
Q2 sin match en maestro: se marca y se lista (propuesto y aceptado en linea general: color + nota visible).
Q3 estandares viejos de IVA/RF por antiguedad: ¿el preliminar propone estandar y Felipe baja a mano, o migrar valores viejos?
Q4 RST_SIMPLE presentada: ¿cuenta como renta OK? (caso Christian Cock).
Q5 git en produccion: ¿cuando hacemos el primer commit? (hoy esta todo staged).

## 6. PENDIENTOS MENORES
- Purga de `__pycache__` de OneDrive (hay .pyc 313 y 314 mezclados; el .gitignore ya no los versiona, falta excluirlos de sync si Felipe quiere).
- SMLV 2026: cuando salga el decreto, actualizar catálogo (CONT_PN, CONT_PJ_C).
- Prueba en el PC de OFICINA despues de que OneDrive sincronice: abrir 5001 y 777, verificar que rutas_comunes resuelve con la letra C (debe: es relativo).
