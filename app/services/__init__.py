"""
Reglas de negocio archivísticas.

Aquí vive la lógica que no depende del transporte web: normalización de fechas,
verificación de hojas de control, herencia de contexto por periodo, armado del
código de referencia y valoración según la Tabla de Valoración Documental.
Los enrutadores llaman a estos servicios; los servicios no conocen a FastAPI.
"""
