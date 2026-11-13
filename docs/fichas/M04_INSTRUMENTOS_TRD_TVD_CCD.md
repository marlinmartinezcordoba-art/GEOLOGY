# M04 · Instrumentos archivísticos: TRD, TVD y CCD

Decisión D-30. Pruebas: `backend/tests/test_m04_instrumentos.py`. Pantalla: proyecto → pestaña **TRD · TVD · CCD**.

## Qué hace

| Paso | Quién | Qué queda |
|---|---|---|
| Crear el instrumento (TRD, TVD o CCD; la TVD con su periodo valorado) | Gestiona instrumentos | Nombre, tipo, periodo |
| Importar una versión desde Excel o CSV | Gestiona instrumentos | El archivo original con su huella SHA-256, cada dependencia, serie y subserie con la hoja y la fila de donde salió, errores, avisos y normalizaciones |
| Revisar | Cualquiera que consulte | Árbol dependencia → serie → subserie con tipos documentales, AG, AC, disposición, soporte y procedimiento |
| Aprobar | Aprueba instrumentos, **otra persona** | Acto administrativo, fecha, convalidación, vigencia, quién y cuándo |
| Descartar un borrador | Gestiona instrumentos | El borrador queda como evidencia |
| Comparar dos versiones | Cualquiera que consulte | Series nuevas, retiradas y modificadas campo por campo |

## Formatos que lee

- **Tabular** (la plantilla que se descarga en la pestaña): una fila por serie o subserie.
- **Formato oficial del AGN:** una hoja por dependencia, con «Oficina productora» y «Código» en el
  encabezado y encabezados de dos niveles (retención AG/AC, disposición CT/E/S/M-D).
- Tipos documentales separados por punto y coma o saltos de línea dentro de la celda.

La lectura es la de Kustos, adaptada: reconoce las columnas por su texto, corrige lo evidente y lo anota
como «normalización». Lo que falta no se completa.

## Reglas

- **TRD:** cada serie o subserie necesita AG, AC y una disposición final. Si falta, es
  error y la versión no se puede aprobar.
- **TVD:** exige la disposición final; los tiempos de retención son opcionales.
- **CCD:** clasifica; no exige retención ni disposición.
- Sin tipos documentales es aviso. Sin soporte se registra híbrido y se anota. Las disposiciones E, S o
  M/D sin procedimiento descrito generan aviso.
- Un borrador a la vez por instrumento.
- La fecha del acto no puede ser futura. La vigencia no puede ser pasada.
- Vigencia desde ahora: reemplaza a la vigente. Con fecha futura: queda **programada** y entra sola.
- Todo queda en la auditoría: crear, importar, aprobar y descartar.

## Uso en los demás módulos

- **M08 FUID:** al validar un FUID, si el proyecto tiene TRD o TVD vigente, cada fila cuyo código de serie
  no esté en ella recibe un aviso. No es error: el fondo puede ser anterior a la TRD.
- **Clasificación:** ver la sección siguiente.

## Clasificación de las unidades (pestaña **Clasificación**)

Pruebas: `backend/tests/test_m04_clasificacion.py`. Decisión D-31.

**Qué instrumento aplica a cada unidad.** Si el proyecto tiene una TVD cuyo periodo contiene las fechas
extremas de la unidad, esa TVD (fondo acumulado). Si no, la TRD vigente. Si solo hay uno, ese.

**Dónde se clasifica.** En la subserie, o en la serie si no tiene subseries. La lista es cerrada: solo
existe lo que dice la versión vigente.

**Clasificar automáticamente** recorre las unidades pendientes:

| Caso | Resultado | Etiqueta |
|---|---|---|
| El código del FUID está **escrito igual** en la tabla | Clasificada (confirmada) | Del FUID |
| El código coincide escrito de otra forma («100.02» frente a «100-02») | Propuesta, confianza media | Por el código del FUID |
| El FUID trae la serie y la serie tiene una sola subserie | Propuesta, confianza alta | Por el código del FUID |
| El FUID trae la serie con varias subseries | Propuesta: la subserie se elige por el nombre | Por el código del FUID |
| Sin código, pero el nombre del expediente se parece al de una subserie | Propuesta, confianza alta o media | Por el nombre |
| Nada coincide, o hay empate | Queda sin clasificar | — |

Cuando el nombre del expediente no se parece en nada al de la subserie propuesta, la confianza baja un
nivel y el «por qué» lo dice. El parecido se mide con el puntaje del motor de clasificación de GEOLOGY.
A diferencia de GEOLOGY, ARCA no propone «la primera de la tabla» cuando nada coincide.

**Decidir.** Las propuestas se confirman o se rechazan (con motivo) por lotes. *Asignar serie o
subserie* clasifica a mano las unidades marcadas. Reclasificar lo ya confirmado exige motivo y la
clasificación anterior queda como «reemplazada».

**La versión se conserva.** Si se aprueba una TRD nueva, lo clasificado sigue con la versión con que se
hizo y aparece en «Con versión anterior». *Pasar a la versión vigente* (con motivo) lo mueve solo donde
la misma serie o subserie sigue existiendo con el mismo código. Lo demás queda para que una persona lo
reclasifique. Una propuesta hecha con una versión que ya no está vigente no se puede confirmar.

**Calendario de retención.** Se calcula desde la fecha final de la unidad:
- fin del archivo de gestión = fecha final + AG;
- fin del archivo central = fin del archivo de gestión + AC.

Con eso, cada unidad muestra en qué fase debería estar hoy (gestión, central o retención cumplida) y su
disposición final. Sin fecha final o sin tiempos (por ejemplo, una TVD), solo se muestra la disposición.
Esto alimenta las transferencias y la disposición final (D-24).

**Alertas.** Aparecen cuando el código del FUID no coincide con la clasificación y cuando la unidad está
clasificada con una versión no vigente.

API `/api/v1/proyectos/{id}/clasificacion`:
- `GET /resumen`
- `GET ?situacion=&alertas=&q=`
- `GET /opciones`
- `POST /proponer`, `/asignar`, `/confirmar`, `/rechazar`, `/actualizar-version`

Permiso: `clasificacion:gestionar` (migración 0006: Administración, Dirección de proyecto y Equipo
operativo). Para consultar basta `inventario:leer`.

Pendiente: clasificar el documento dentro del expediente por tipo documental, a partir del OCR (M13–M16).

## API

`/api/v1/proyectos/{id}/instrumentos`: `GET` lista con versiones · `POST` crear · `GET /plantilla?tipo=` ·
`POST /{inst}/versiones` (archivo, motivo) · `GET /{inst}/versiones/{v}` detalle con elementos ·
`GET /{inst}/versiones/{v}/archivo` original · `POST /{inst}/versiones/{v}/aprobar` ·
`POST /{inst}/versiones/{v}/descartar` · `GET /{inst}/comparar?desde=&hasta=`.

Permisos: `instrumentos:leer`, `instrumentos:gestionar`, `instrumentos:aprobar` (migración 0005 los da a
los roles base: Administración y Dirección de proyecto los tres; Equipo operativo y Consulta, leer).
