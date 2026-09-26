# Sistema de Cobros

Sistema para llevar el control de las **Cuentas de Cobro** anuales: quién ha pagado,
quién no, qué medio se usó para el envío, fechas, pagos, abonos, autodescuentos y observaciones.

## Cómo iniciar

1. **Solo la primera vez (o al cambiar de PC):** doble clic a **`instalar_venv.bat`**:
   pregunta en qué carpeta guardar el entorno virtual (por defecto `C:\EntornosPython\SistemaCobros-venv`,
   FUERA de OneDrive para que no infle tus respaldos) e instala las dependencias.
2. Después, todos los días: doble clic a **`INICIAR.bat`**.
3.. Se abre tu navegador en `http://localhost:5001` (el .bat lo abre automáticamente).
4.. Esa ventana negra debe quedar abierta mientras usas el sistema; para cerrar el sistema, ciérrala.

> El puerto es **5001** porque el 5000 ya lo usa el sistema Maestro.

## Entorno virtual (venv)

- El venv **ya no vive dentro de esta carpeta**: OneDrive no lo sincroniza ni lo respalda
  (pesa cientos de MB y en respaldos no sirve de nada: solo funciona en el PC donde se creó).
- Cada PC anota la ruta de su venv en una carpeta **local**
  (`%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt`); esa copia es la que manda. El archivo
  `entorno_venv.txt` del proyecto es solo referencia (OneDrive lo sincroniza entre PCs, así que
  puede mostrar la ruta del otro equipo).
- **Cambiar la ubicación del venv:** corre `instalar_venv.bat` de nuevo y elige otra carpeta.
- **En otro PC:** corre `instalar_venv.bat` en ese PC; cada PC tiene su propio venv en una carpeta
  local. Por OneDrive solo viajan el código y la base de datos (`instance/cobros.db`), que es lo importante.
- **Para revisar qué entorno usa este PC:** abre `entorno_venv.txt` con el Bloc de notas.

## Primer uso

1. En el **Resumen**, botón "Importar Excel" → sube `Recursos/0-Presupuesto de cobros 2025 -FBZ.xlsx`.
   Esto carga clientes activos, presupuestos y las cuentas 26-001…26-005 con su estado real (ya viene importado de fábrica; reimportar es seguro y acumulativo).
2. Revisa **Grupos Familiares** y ancla los miembros + marca el **pagador**.
3. Todo lo demás (emisor, datos bancarios, IPC, mínimas, concepto del PDF) está en **Parámetros**.

## Estructura

```
Sistema de Cobros/
├── INICIAR.bat          ← doble clic para arrancar
├── instalar_venv.bat     <- instalador: crea el venv fuera de OneDrive (pregunta donde)
├── entorno_venv.txt      <- ruta del venv de este PC (la escribe el instalador)
├── run.py               ← entry point (puerto 5001)
├── requirements.txt
├── Recursos/            ← tu Excel guía y PDFs de ejemplo
├── instance/            ← base de datos SQLite (cobros.db) y PDFs generados
└── app/
    ├── __init__.py      ← factory de Flask
    ├── models.py        ← modelos (Cliente, CuentaCobro, Pago, Ajuste, Envíos, Años…)
    ├── routes.py        ← todas las pantallas
    ├── importar.py      ← lector del Excel
    ├── pdf_generator.py ← generador del PDF minimalista
    └── templates/       ← interfaz (Bootstrap 5)
```

## Datos clave

- **Base de datos**: `instance/cobros.db` (SQLite, un solo archivo, al lado de `app/`). Para respaldar, copia ese archivo.
- **PDFs generados**: `instance/pdfs/<año>/<prefijo>-<número>.pdf`
- **Entorno virtual**: vive fuera del proyecto (ruta en `entorno_venv.txt`) para que OneDrive no lo
  copie; se reconstruye con `instalar_venv.bat` cuando haga falta.

## Reglas de negocio implementadas

- Numeración `26-001`, `26-002`… automática, **reinicia cada año** con prefijo parametrizable.
- **Anulación**: la cuenta queda ANULADA conservando el número; **nunca se reutiliza** (el consecutivo sigue avanzando).
- **Cuentas compartidas** (familias): una cuenta tiene varias líneas, una por cliente, cada una con su valor; el PDF las lista.
- **Pagador del grupo**: campo por cliente; la cuenta sale "DEBE A" del pagador pero con línea por cada miembro.
- **Autodescuento**: la cuenta se emite completa; el descuento se registra como *ajuste* con motivo y el pago real como *pago*. El presupuesto del año próximo arrastra el **valor de la cuenta**, no el pagado (el pagado queda como referencia).
- **Abonos parciales**: se registran varios pagos; el saldo se calcula solo.

## Qué hacer cuando cambie el año

1. Ve a **Años** → crea el año nuevo (ej. 2027). El sistema trae: prefijo `27`, gravable 2026,
   mínimas aumentadas por el IPC, concepto nuevo y los **presupuestos arrastrados** (último valor emitido × IPC).
2. Revisa los presupuestos arrastrados (Clientes → editar) y ajusta los que toquen.
3. Activa el año nuevo.

## Próximas fases (ya dejado el diseño listo)

- Fase 2: exporte consolidado a Excel, valor en letras en el PDF, búsqueda global.
- Fase 3: registro de facturas DIAN (GTFF-xxx) para consolidado, vencimientos, cálculo de retención por grupo pagador.
