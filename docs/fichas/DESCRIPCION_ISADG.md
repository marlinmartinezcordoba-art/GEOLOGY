# Procesos por lote y descripción ISAD(G) sobre lo digitalizado

Decisiones D-26 y D-36. Pruebas: `backend/tests/test_descripcion.py` y, para la independencia,
`backend/tests/test_motor.py`. Pantallas:
- proyecto → pestaña **Descripción ISAD(G)** (qué lleva cada lote y bandeja);
- **Describir / Revisar** → página de la descripción;
- **Ver los documentos** → el visor de la hoja de control.

## Qué lleva cada lote (D-26)

- El lote es el de la **base de cajas** (Productividad). Cada lote dice si lleva **hoja de control**,
  **descripción ISAD(G)** o **ambas**; al menos una.
- Lo que no se configure toma lo del proyecto. Si nadie configuró el proyecto, lleva hoja de control y no
  ISAD(G).
- Lo configura la dirección del proyecto, con motivo, y queda en la auditoría.
- Si el lote no lleva hoja de control, no se crea y la bandeja la muestra como «No aplica». Igual con la
  descripción.
- La configuración vive en un módulo propio (`modulos/procesos`). Así la hoja de control no depende de la
  ISAD(G) ni la ISAD(G) de la hoja de control. Lo comprueba una prueba automática.

## Cómo se construye la descripción

- **Independiente del ciclo vital (D-24):** se describe donde esté la unidad.
- **Depende de la digitalización:** solo se describe lo digitalizado.
  - Si el lote lleva hoja de control, usa la **hoja verificada**. Mientras no lo esté, se avisa y se puede
    recalcular después.
  - Si el lote no lleva hoja, usa lo que **leyó el OCR**: documentos reconocidos y sus fechas.

| Elemento | De dónde sale |
|---|---|
| 3.1.1 Código de referencia | Calculado: país, código del proyecto, código de la clasificación e identificador |
| 3.1.2 Título | **Propuesto** desde el tipo documental que predomina y la dependencia (motor de GEOLOGY); lo escribe o confirma una persona |
| 3.1.3 Fechas extremas | Hoja de control verificada; si no hay, OCR (por confirmar); si no, FUID |
| 3.1.4 Nivel | Expediente |
| 3.1.5 Volumen y soporte | Folios contados en la hoja (o FUID), metros lineales e imágenes digitales |
| 3.2.1 Productor | Entidad del proyecto y dependencia de la clasificación |
| 3.2.3 Historia archivística | Caja y carpeta, y los movimientos de fase registrados (transferencias) |
| 3.2.4 Forma de ingreso | «Transferencia secundaria» si llegó así al histórico; si no, la persona |
| 3.3.1 Alcance y contenido | **Propuesto** desde los trámites (o los documentos del OCR); lo completa o confirma una persona |
| 3.3.2 Valoración | Disposición, retención y procedimiento de la TRD o TVD con su acto. No se edita: se hereda |
| 3.3.4 Organización | Orden y foliación de la hoja |
| 3.4.1 Acceso | Acceso de la TRD (pública, clasificada o reservada, Ley 1712 de 2014) |
| 3.4.3 Lengua · 3.4.5 Instrumentos · 3.5.2 Copias · 3.7.2 Reglas | Calculados desde lo que existe en ARCA |
| 3.7.1 Nota del archivero · 3.7.3 Fecha | Al aprobar: quién elaboró, quién revisó y cuándo |

**Recalcular lo deducido** vuelve a tomar los datos (por ejemplo, al verificarse la hoja) sin tocar lo que
escribió o confirmó una persona.

## Revisión y aprobación

- Antes de enviar se corren las **reglas de revisión del motor de GEOLOGY**: obligatorios, título que
  identifique la unidad (no genérico), título coherente con la clasificación, fechas iguales a la hoja de
  control, alcance que aporte, volumen con soporte y folios que cuadren.
  - **Incumple** (DEVUELVE): impide enviar.
  - **Revise**: queda a la vista.
- Las propuestas sin confirmar también impiden enviar.
- La aprueba **otra persona**, con los documentos a la vista. Puede devolver con una observación por
  elemento, y una descripción aprobada solo se cambia reabriéndola con motivo.

## Expedir

La **base de descripción ISAD(G)** sale en la plantilla de la entidad: tipo nuevo `descripcion_isadg`,
parametrizable y con formato base. Trae una fila por unidad aprobada con todos los elementos y queda en
Entregables con su huella.

## API

- `GET|PUT /api/v1/proyectos/{id}/procesos-por-lote`
- `/api/v1/proyectos/{id}/descripciones`:
  - bandeja · `POST /expedir`
  - `GET|POST|PATCH /unidades/{u}`
  - `POST /unidades/{u}/confirmar`, `/recalcular`, `/enviar`, `/aprobar`, `/devolver`, `/reabrir`

Permisos (migración 0011):
- `descripcion:elaborar`: Administración, Dirección de proyecto y Equipo operativo.
- `descripcion:aprobar`: Administración y Dirección de proyecto.
- Configurar lotes: `proyectos:gestionar`.

## Pendiente

- Redacción del título y del alcance con un modelo de lenguaje: el motor ya la tiene (`motor/isadg/redaccion.py`)
  y queda para cuando haya proveedor configurado (M27). Siempre como propuesta.
- Descripción en niveles superiores (fondo, sección, serie) y exportación EAD.
