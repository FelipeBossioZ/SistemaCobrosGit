# -*- coding: utf-8 -*-
"""Punto de entrada del Sistema de Cobros. Puerto 5001 (5000 lo usa el Maestro)."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
