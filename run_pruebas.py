# -*- coding: utf-8 -*-
"""SISTEMA DE PRUEBAS - puerto 777. BD propia (copia). Produccion sigue en 5001."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=777, debug=True)
