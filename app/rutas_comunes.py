# -*- coding: utf-8 -*-
"""Rutas comunes del proyecto (sin letras de disco hard-codeadas).

El punto de partida es SIEMPRE la carpeta del propio proyecto (carpeta app/
de este archivo). Arbol real sincronizado por OneDrive (igual en ambos PCs):

    <OneDrive>/OFICINA/FELIPE/Oficina Felipe/
        |- 1- PLANIFICACION OFICINA/2026/Sistema maestro/sistema-maestro-v7
        |- 6-Presupuestos/
             |- 0-Presupuesto de cobros <anio> -FBZ.xlsx   (si esta en la raiz)
             |- Sistema de Cobros/Recursos/...             (o aqui)
             |- SistemaPruebas/

Asi el maestro y el Excel del ano anterior se resuelven relativos al proyecto
y funcionan igual con la letra Z (casa) o C (oficina), en cualquier PC.
Los parametros ruta_maestro / excel_cobros_anterior siguen funcionando como
OVERRIDE manual; y _rebase() queda como tercera red de seguridad.
"""
import os

_DIR_APP = os.path.dirname(os.path.abspath(__file__))          # ...\app
_DIR_PROYECTO = os.path.dirname(_DIR_APP)                      # ...\Sistema xxx
_DIR_6P = os.path.dirname(_DIR_PROYECTO)                       # ...\6-Presupuestos
_DIR_FELIPE = os.path.dirname(_DIR_6P)                         # ...\Oficina Felipe

NOMBRE_MAESTRO = "sistema-maestro-v7"


def ruta_maestro_defecto():
    """Carpeta del Sistema Maestro relativa al proyecto (independiente de la letra)."""
    return os.path.join(_DIR_FELIPE, "1- PLANIFICACIÓN OFICINA", "2026",
                        "Sistema maestro", NOMBRE_MAESTRO)


def excel_anterior_defecto(anio_cobro_anterior=2025):
    """Excel del presupuesto del ano anterior. Prueba la raiz de 6-Presupuestos
    y las carpetas Recursos de ambas instalaciones; devuelve el primero existente."""
    nombre = "0-Presupuesto de cobros %d -FBZ.xlsx" % anio_cobro_anterior
    candidatos = [
        os.path.join(_DIR_6P, nombre),
        os.path.join(_DIR_6P, "Sistema de Cobros", "Recursos", nombre),
        os.path.join(_DIR_6P, "SistemaPruebas", "Recursos", nombre),
    ]
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return candidatos[0]
