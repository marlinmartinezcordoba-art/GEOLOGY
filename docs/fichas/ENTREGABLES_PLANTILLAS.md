# Entregables · Plantillas de la entidad versionadas (FUID de salida, rótulos de caja y de carpeta)

Decisión D-27. Pruebas: `backend/tests/test_entregables.py`.

## Cómo se parametriza sin tocar el código

1. La entidad entrega su formato en Excel, o se parte del **formato base** de ARCA (sin datos).
2. En cada casilla se escribe el marcador del dato: `{{caja}}`, `{{fecha_inicial}}`, `{{entidad_cliente}}`…
   - Si la casilla solo tiene el marcador, el valor conserva su tipo (número o fecha).
   - Si va dentro de un texto («Proyecto {{codigo_proyecto}}»), se reemplaza en el texto.
3. Para la tabla se escribe **una sola fila modelo** con `{{fila.identificador}}`, `{{fila.nombre}}`… ARCA
   la repite por cada expediente con su formato. Lo que está debajo (totales, firmas) baja con sus celdas combinadas.
4. En los rótulos, la hoja es **un rótulo**: ARCA saca una hoja por caja o por carpeta. En el rótulo de
   caja, la fila modelo lista las carpetas de esa caja.
5. **Valores fijos** de la versión: datos de la entidad que no salen del sistema (por ejemplo, la entidad
   productora como la escribe la entidad). Si se dejan vacíos, se usa el dato del proyecto.

Si el formato pide un marcador que ARCA no conoce, la versión se rechaza diciendo cuál. Nunca queda una
casilla vacía en silencio.

## Versiones

- Una versión no se edita: se publica otra, con motivo y código del formato.
- **Vigente desde ahora:** reemplaza la vigente, que queda como «reemplazada».
- **Con fecha futura:** queda «programada» y entra sola en su fecha.
- La vigencia no puede ser pasada.
- **Ámbito:** la plantilla del proyecto prevalece sobre la de la organización.
- Cada **expedición** guarda el archivo producido (con su huella SHA-256), la versión usada, el filtro
  (cajas o lote) y quién la hizo. Lo ya expedido conserva la versión con que se hizo, aunque después se
  reemplace la plantilla.

## Marcadores disponibles

Se consultan en la pantalla (*Ver marcadores*) o en `GET /api/v1/plantillas/tipos`.

- **Comunes:** entidad, nit, proyecto, codigo_proyecto, entidad_cliente, contrato, fecha, codigo_formato, version_formato.
- **FUID:** totales (unidades, folios e imágenes) y, por fila, número de orden, identificador, código de serie, nombre, fechas, caja, carpeta, tomo, otro, folios, soporte, frecuencia, notas, imágenes digitalizadas y estado de la digitalización.
- **Rótulo de caja:** caja, frente, lote, sede, ubicación, carpetas, primera y última unidad, fechas extremas, series y folios de la caja, y la fila de cada carpeta.
- **Rótulo de carpeta:** todos los datos de la unidad documental.

## API

- `GET /plantillas/tipos` · `GET /plantillas/tipos/{tipo}/base`
- `GET/POST /plantillas` · `POST /plantillas/{id}/versiones` (archivo, motivo, código, valores fijos, vigencia) · `GET /plantillas/versiones/{id}/archivo`
- `POST /proyectos/{id}/entregables` (tipo, cajas, lote, plantilla) · `GET …/entregables` · `GET …/entregables/{id}/archivo`

## Pendiente

- PDF listo para imprimir.
- Copiar imágenes (logos) en las hojas de rótulos generadas: hoy se conservan en el FUID, pero no en las copias de hoja.
- Hoja de control con plantilla de la entidad, cuando llegue M14.
- La TRD como instrumento versionado (M04) usará el mismo esquema de versiones con vigencia.
