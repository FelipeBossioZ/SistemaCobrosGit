# Sistema de PRUEBAS (puerto 777)

- Es una copia completa del sistema de produccion (carpeta Sistema de Cobros, puerto 5001).
- Tiene **BD propia**: copia hecha el 24/09/2026. Lo que pase aqui NO afecta produccion.
- Los PDF, correos .eml e imagenes que genere aqui van a `salidas\` (NO a las carpetas reales).
- Para arrancar: doble clic a `iniciar_pruebas.bat` (o `python run_pruebas.py` con el venv).
- Produccion sigue funcionando igual en el puerto 5001. Pueden estar los dos abiertos a la vez.
- Cuando una funcion se apruebe aqui, se copia el codigo a produccion SIN tocar la BD de produccion
  (solo se agregan tablas nuevas; clientes, cuentas, pagos y notas quedan intactos).
