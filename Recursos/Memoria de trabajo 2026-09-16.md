# Memoria de trabajo — 16 de septiembre de 2026
## Sistema de Cobros — reparación y puesta a punto en el PC de la oficina (PEPPA-BOSS)

---

## Contexto del día

El sistema fue creado en otro PC (unidad **Z:**, Python 3.13 en `C:\Python313`) y al traerlo
a la oficina no arrancaba: `ModuleNotFoundError: No module named 'flask_sqlalchemy'`.
Un agente anterior pasó una hora trabajando sobre el diseño del PDF sin resolver el problema
real (el entorno virtual roto), y dejó el PDF revertido a la versión paisaje vieja.

**Lo importante: el código y la base de datos nunca se dañaron.** Los 183 clientes y todas
las cuentas siguieron intactos todo el tiempo.

---

## 1. Diagnóstico de la mañana (9:00 a.m.)

- El `venv` dentro de la carpeta de OneDrive fue creado en el PC viejo: `pyvenv.cfg` apuntaba
  a `Z:\...` y `activate.bat` tenía grabada esa ruta. En este PC no existe `Z:` ni `C:\Python313`.
- Verificado contra el respaldo: `models.py` idéntico, `routes.py` intacto, sintaxis de los
  5 archivos `.py` correcta, base de datos intacta (`instance/cobros.db`, 183 clientes).

## 2. Reparación del arranque (9:30 a.m.)

1. **Borrado el venv roto** que estaba dentro de la carpeta de OneDrive (no sirve tenerlo ahí:
   pesa cientos de MB y un venv solo funciona en el PC donde se creó).
2. **Venv nuevo en `C:\EntornosPython\SistemaCobros-venv`** (fuera de OneDrive) con el
   Python 3.14 de este PC. Dependencias instaladas: Flask 3.1.3, Flask-SQLAlchemy 3.1.1,
   openpyxl 3.1.5, reportlab 5.0.1, pywin32 312.
3. **`iniciar.bat` nuevo**: lee la ruta del venv desde configuración, muestra qué entorno usa
   y abre `http://localhost:5001`.
4. **`instalar_venv.bat` nuevo (instalador)**: para cualquier PC, pregunta dónde guardar el
   venv (sugiere `C:\EntornosPython\SistemaCobros-venv`), avisa si la ruta contiene "onedrive",
   crea el entorno e instala dependencias solo.
5. **Multi-PC sin peleas**: la ruta que manda en cada PC vive en una carpeta LOCAL
   (`%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt`) que OneDrive no sincroniza. El archivo
   `entorno_venv.txt` del proyecto es solo referencia.
6. `readme.md` actualizado con la sección "Entorno virtual (venv)".

## 3. Restauración del PDF vertical nuevo (2:30 p.m.)

- Felipe reportó que su **versión vertical aprobada (15-sep, v2)** fue reemplazada por la
  versión paisaje vieja que dejó el agente, y que el botón de descarga dejó de funcionar.
- **PDF restaurado**: `Respaldo codigo 2026-09-16/pdf_generator.py.bak` → `app/pdf_generator.py`.
  La copia paisaje del agente quedó guardada como
  `Respaldo codigo 2026-09-16/pdf_generator.PAISAJE_agente_16sep.bak`.
- **Botón de descarga**: el código estaba bien; el problema era el parámetro
  `carpeta_pdfs_envio` apuntando a `Z:\OneDrive\...` (PC viejo). Corregido en la base de datos a
  `C:\OneDriveOficina\OneDrive\OFICINA\FELIPE\Oficina Felipe\6-Presupuestos\Cuentas de Cobro`.
  Respaldo previo de la DB: `Respaldo codigo 2026-09-16/cobros.antes-fix-carpeta.db`.

## 4. Fantasma descubierto y eliminado (2:40 p.m.)

- El agente anterior también había creado venvs duplicados en
  `C:\Users\Usuario\Desktop\EntornosVirtuales\` (SistemaCobros, SistemaMaestro, DonPeppiniContadore)
  y quedó un **servidor viejo corriendo desde las 11:02 a.m.** con el PDF paisaje en memoria,
  pisando el puerto 5001.
- Se cerraron todos los servidores duplicados y se dejó un solo entorno oficial:
  `C:\EntornosPython\SistemaCobros-venv`.
- **`iniciar.bat` blindado**: ahora avisa con un mensaje claro si el puerto 5001 ya está ocupado
  (instancia olvidada) en vez de fallar de forma confusa.

## 5. Verificación final (2:48 p.m.)

Prueba de punta a punta ejecutando el `INICIAR.bat` real:
- App arriba: HTTP 200 en `http://localhost:5001` ✅
- Botón "Descargar a carpeta": generó el PDF ✅
- PDF `OCHOA_VELASQUEZ_RAFAEL_CdeC_26_001.pdf` regenerado **VERTICAL confirmado** (612×792) ✅
- Puerto 5001 liberado al terminar, listo para el doble clic del usuario ✅

---

## Guía rápida para después

| Quiero... | Hago... |
|---|---|
| Arrancar el sistema | Doble clic a `INICIAR.bat` |
| Instalar el sistema en otro PC | Doble clic a `instalar_venv.bat` en ese PC y elegir carpeta (que no sea OneDrive) |
| Ver qué venv usa este PC | La primera línea al arrancar dice `Entorno: <ruta>` (o abrir `%LOCALAPPDATA%\SistemaCobros\entorno_venv.txt`) |
| Cambiar la ubicación del venv | Correr `instalar_venv.bat` de nuevo con otra carpeta |
| Respaldar los datos | Copiar `instance/cobros.db` (es el único archivo de datos) |

**Espacio que puedes liberar**: el venv `C:\Users\Usuario\Desktop\EntornosVirtuales\SistemaCobros`
ya no se usa y puedes borrarlo. **NO borrar** `SistemaMaestro` ni `DonPeppiniContadore`
(parecen entornos de los otros sistemas).

**Respaldos creados hoy** (carpeta `Respaldo codigo 2026-09-16`):
- `iniciar.bat.bak` — el bat anterior a los cambios
- `pdf_generator.PAISAJE_agente_16sep.bak` — la versión paisaje que dejó el agente
- `cobros.antes-fix-carpeta.db` — la base de datos antes de corregir la carpeta de descarga
