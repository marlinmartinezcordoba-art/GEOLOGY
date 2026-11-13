"""Descripción archivística ISAD(G) (NTC 4095): independiente de la digitalización y de la hoja de control.

- `descripcion`: elementos de la norma calculados por reglas (extensión, productor, valoración…).
- `redaccion`: los elementos narrativos que redacta un modelo, siempre marcados como propuesta.
- `revision` y `revisor`: control de calidad de la descripción, por reglas y por un segundo modelo.

Trabaja sobre lo digitalizado. Ningún módulo fuera de este paquete lo importa, y este paquete no importa
la hoja de control: cada lote decide si se le hace hoja de control, ISAD(G) o ambas (D-24 y D-26).
"""
