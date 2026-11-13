# Automatización completa y paquete de entrega

Decisión D-40. Pruebas: `backend/tests/test_automatizacion.py`. Pantallas: la hoja de control (bloque
**Metadatos del documento** de cada trámite) y el proyecto → pestaña **Entregables** → **Paquete de entrega
digital**.

ARCA no es un SGDEA (D-38). Su trabajo es automatizar lo más posible la digitalización, la calidad, la hoja
de control y los metadatos, y entregar el resultado. Esta ficha reúne lo que se agregó para eso.

## 1. Metadatos de cada documento desde el OCR

Al proponer la hoja desde el OCR, ARCA lee también, por cada documento:

| Metadato | De dónde sale |
|---|---|
| Asunto | El renglón «Asunto:» o «Ref.:» (o el renglón siguiente si va solo) |
| Destinatario | «Para:», «Destinatario:» o el nombre que sigue a «Señor(a)», «Doctor(a)»… en la primera página |
| Remitente | «De:», «Remitente:» |
| Firmantes | El nombre y el cargo después de «Atentamente», «Cordialmente»…; o «Presidente:», «Secretario:», «Elaboró:»… |
| Lugar | La ciudad que va antes de la fecha («Ciudad Ficticia, 5 de marzo de 2021»). No se toma «Comité directivo» ni palabras parecidas |
| Número | El número del título, como está escrito («045») |

- Solo se propone lo que está escrito con su rótulo o en su lugar de costumbre. Lo que no está no se inventa.
- Cada metadato guarda la página y el renglón de donde salió, y queda **por confirmar**: bloquea el envío
  de la hoja hasta que una persona lo confirme o lo corrija, como el resto de lo propuesto por el OCR.
- Los metadatos verificados van a la hoja expedida en el formato de la entidad (marcas `{{fila.asunto}}`,
  `{{fila.remitente}}`, `{{fila.destinatario}}`, `{{fila.firmantes}}`, `{{fila.lugar}}`, `{{fila.numero}}`),
  a la consulta (se pueden buscar) y al alcance de la descripción ISAD(G).

## 2. Calidad de lo digitalizado antes y después del OCR

- **Páginas giradas.** Antes de leer, ARCA detecta la orientación de cada página (Tesseract OSD) y la
  endereza. Si el detector duda (pasa en páginas con poco texto), lee de las dos formas y se queda con la
  lectura más confiable. El giro queda guardado y el visor muestra la página derecha. El original no se toca.
- **Legibilidad.** Al terminar el OCR, el flujo y la validación de la hoja avisan las páginas con confianza
  baja (menos de 60 %), sin texto o giradas, para que calidad las mire.

## 3. El FUID de salida con los folios contados

Si el expediente tiene hoja de control verificada, el FUID de salida lleva los folios y las fechas extremas
de la hoja (lo contado sobre lo digitalizado), no lo que traía el inventario de origen. Cuando no coinciden
queda la constancia en las notas: «Folios contados en la hoja de control: 6; el inventario de origen
declaraba 10». Marcas nuevas: `{{fila.folios_inventario}}` y `{{fila.origen_folios}}`.

## 4. Productividad contada por ARCA

Fuentes automáticas nuevas para las actividades (columna `Fuente_Automatica` de `dActividades`):
`paginas_ocr`, `hojas_verificadas`, `folios_verificados`, `documentos_hoja` y `descripciones_aprobadas`.
Se cuentan solas por día y turno, como las imágenes y los expedientes inventariados.

## 5. Paquete de entrega digital

Es lo que ARCA entrega para cargar en el SGDEA de la entidad. Se pide desde Entregables (con los filtros de
cajas y de lote) y se arma en segundo plano, en la cola de trabajos (D-39).

Un ZIP con una carpeta por expediente:

| Archivo | Contenido |
|---|---|
| `expediente.pdf` | Las páginas en orden y derechas, con el texto del OCR debajo de la imagen: se puede buscar y copiar. Sin OCR en el servidor, solo las imágenes |
| `metadatos.json` | FUID; clasificación con la TRD, el acto, el acceso, la disposición y la retención; hoja de control verificada (cada documento con tipo, fecha, folios, páginas y metadatos); descripción ISAD(G) aprobada; fase; archivos originales con su huella y su calidad |
| `hoja_control.csv` | Si tiene hoja verificada |

En la raíz: `manifiesto.csv` (huella SHA-256 de cada archivo del paquete), `originales.csv` (huella de
cada original recibido), `pendientes.csv` (qué expedientes no entraron y por qué) y `LEAME.txt`.

- Por defecto entra **solo lo que está listo** según lo que lleva su lote: hoja verificada si la lleva y
  descripción aprobada si la lleva. Se puede desmarcar para un paquete de avance.
- Hasta 500 expedientes por paquete (se arman por caja o por lote).
- El ZIP queda en el almacén con su huella; descargarlo la comprueba. Pedir, generar y descargar quedan en
  la auditoría.
- Permisos: lo pide y lo descarga quien puede expedir entregables; la lista la ve quien lee el inventario.

## Lo que falta

- **PDF/A certificado.** El PDF del paquete tiene texto buscable, pero no es PDF/A validado. Requiere
  instalar OCRmyPDF y Ghostscript en el servidor.
- **Logos en los documentos expedidos en PDF.** Hoy se expiden en el Excel de la entidad.
