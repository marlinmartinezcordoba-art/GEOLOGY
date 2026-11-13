# M24 · Productividad, base de cajas y Power BI

Usa el **diseño** del reporte de productividad para Power BI (hojas, columnas, llaves y cálculos) y ningún
dato de ninguna entidad ni proyecto (D-29). Pruebas: `backend/tests/test_m24_productividad.py`.

## Modelo (el mismo de Power BI)

| Tabla | Hoja del libro | Tipo | Llave |
|---|---|---|---|
| dFrentes | dFrentes | configuración | Cod_Frente |
| dActividades | dActividades | configuración | Actividad_Clave (+ `Fuente_Automatica`, agregada por ARCA) |
| dMetas | dMetas | configuración | Actividad_Clave + Turno |
| dTurnos · dCalendario · dPersonal | ídem | configuración | Turno · Fecha · Frente |
| fProduccion | Registro_Produccion | registro diario | Fecha, Turno, Actividad, Caja_Desde, Caja_Hasta |
| fCalidad · fNovedades · fEntregas | Registro_* | registro diario | Fecha, Cod_Frente |
| dCajas | — | base de cajas del proyecto | Caja |
| Tablero | — | calculado | Frente |

## Tablero (mismas fórmulas del diseño)

- **Fecha de corte:** la última fecha con producción, o la que se escoja.
- **Acumulado:** suma de la actividad de avance del frente hasta el corte.
- **Producido en el corte:** lo mismo, pero solo en el día del corte.
- **Meta diaria:** suma de `Meta_Turno` de esa actividad.
- **Días operativos restantes:** días del calendario marcados como operativos, después del corte y hasta el fin del frente.
- **Ritmo requerido:** (volumen − acumulado) ÷ días restantes.
- **Estado:** Terminado · Por iniciar · En ritmo (ritmo ≤ meta) · Atención (hasta 15 % sobre la meta) · En riesgo.
- **Además:** calidad por frente (lotes, rechazos, críticos), novedades abiertas, cantidad aceptada por la entidad y producción por turno.

En ARCA el tablero se recalcula cada 30 segundos.

## Conteo automático

Una actividad con `Fuente_Automatica` suma sola lo que pasa dentro de ARCA, por día y por turno según el
horario de `dTurnos`:

- `imagenes_recibidas`: las imágenes que entran a la bandeja de calidad;
- `imagenes_aprobadas`: las que aprueba el control de calidad;
- `expedientes_inventariados`: las unidades integradas desde el FUID.

## Base de cajas: qué está procesado y qué falta

- Se carga desde un listado en Excel o CSV (`Caja` obligatoria; opcionales `Carpetas`, `Cod_Frente`, `Lote`, `Sede`, `Ubicacion`, `Notas`), o se arma desde el FUID integrado agrupando por caja y contando carpetas.
- Los rangos `Caja_Desde`–`Caja_Hasta` de la producción marcan cada caja como hecha en esa actividad. Se comparan por número cuando las cajas comparten prefijo.
- **Procesada:** ya pasó por la actividad de avance de su frente. **En proceso:** pasó por otra actividad. **Pendiente:** no ha pasado por ninguna.
- Hay resumen por frente (cajas y carpetas) y filtros por estado, frente y número de caja.

## Power BI

- Llaves de solo lectura por proyecto (`arca_pbi_…`). Se crean desde la pantalla, se muestran una sola vez, se guardan como huella SHA-256 y se revocan con motivo. Si la organización se suspende, dejan de funcionar.
- `GET /api/v1/powerbi/tablas` y `GET /api/v1/powerbi/{tabla}?formato=json|csv`, con el encabezado `Authorization: Bearer <llave>`.
- La pantalla entrega la consulta de Power Query lista para pegar. En el servicio de Power BI se configura con credencial Anónima y la opción Omitir la prueba de conexión.

## Libro de Excel

- **Plantilla vacía** con el diseño (y la hoja Listas), para diligenciar.
- **Importar:** las hojas `d*` reemplazan la configuración; las `Registro_*` se agregan sin duplicar y omiten las «FILA DE EJEMPLO».
- **Descargar el libro lleno**, con el mismo diseño.

## Permisos

- `productividad:leer`: Administrador, Dirección, Equipo, Consulta y Entidad cliente (solo sus proyectos).
- `productividad:registrar`: Administrador, Dirección y Equipo.
- `productividad:configurar`: Administrador y Dirección.

## Pendiente

Editar frentes y metas desde formularios (hoy se hace con el libro). Gráficos de tendencia diaria. Importar
`Registro_*` desde una carpeta compartida programada.
