# Incremento 2A · Inventario FUID, carga desde carpeta y control de calidad

Fichas según el §3 de las Instrucciones v1. Cada criterio de aceptación remite a su prueba
automática: `backend/tests/test_m08_fuid.py` y `backend/tests/test_m10_digitalizacion.py`.

## M08 · Inventarios y FUID

| Campo | Contenido |
|---|---|
| Objetivo | Importar el FUID del proyecto y convertir cada fila válida en una unidad documental, que es lo que luego se digitaliza. |
| Actores | `inventario:gestionar` (Administrador y Dirección de proyecto) importa, mapea, integra y descarta. `inventario:leer` (además el Equipo operativo y Consulta) solo consulta. La Entidad cliente no lo ve. |
| Pantalla | Proyecto › **Inventario FUID**: importar, ver lotes, filas con errores, ajustar columnas, integrar con motivo, buscar unidades. |
| API | `POST /proyectos/{id}/inventario/lotes` (archivo) · `GET …/lotes` · `GET …/lotes/{lote}/filas?solo_errores=` · `PUT …/lotes/{lote}/mapeo` · `POST …/integrar` · `POST …/descartar` · `GET …/unidades?q=` · `GET …/campos`. |
| Flujo | Cargar Excel o CSV → ubicar el encabezado (de uno o dos niveles, como el del AGN) → reconocer las columnas → validar cada fila → reportar errores y avisos → ajustar columnas si hace falta → integrar las filas válidas. |
| Reglas | El archivo fuente queda en el repositorio con su huella. Cada fila se guarda tal como llegó, junto a su valor normalizado. Son **errores**: falta el identificador o el nombre, una fecha no se reconoce, la fecha inicial es posterior a la final, los folios no son un número, o el identificador está repetido en el archivo o ya existe en el proyecto. Son **avisos**: sin fechas (s.f.), sin folios, sin unidad de conservación. Integrar con filas rechazadas exige motivo y deja la conciliación exacta. Nada se completa por inferencia. |
| Pendiente | Validar la serie contra la TRD vigente (llega con M04). Exportar el FUID de salida (llega con los entregables). |

## M10 · Recepción de lo digitalizado (carga desde carpeta)

| Campo | Contenido |
|---|---|
| Actores | `captura:cargar` (Administrador, Dirección y Equipo operativo). |
| Pantalla | Proyecto › **Digitalización y calidad** › *Cargar carpeta* (la carpeta completa de la entrega) o *Archivos sueltos*. La pantalla reparte miles de archivos en envíos pequeños y muestra el avance. |
| API | `POST /proyectos/{id}/digitalizacion/archivos` (archivos + `rutas_relativas`) · `GET …/resumen` · `GET …/unidades?filtro=` · `GET …/archivos?estado=` · `GET …/archivos/{id}/contenido`. |
| Identificación | Por el nombre del archivo (`CP-00374.pdf`, `CARPETA_00374-2.pdf`, `… parte 3.pdf`) o por la subcarpeta (`CP-00374/0001.tif`), comparando la clave normalizada con el inventario. Si el prefijo difiere del FUID, se reconoce por el número cuando no hay ambigüedad. Lo que no se reconoce queda **sin identificar**, para asignarlo a mano. |
| Reglas | El original se guarda una vez, nunca se sobrescribe, y su formato se identifica por la firma interna. El mismo archivo (misma huella SHA-256) no entra dos veces. Nada se reordena ni se elimina: lo que falta se señala. |

## M11 · Control de calidad y perfil de digitalización

| Campo | Contenido |
|---|---|
| Perfil (configurable) | Formas de entrega, formatos, resolución mínima, color mínimo, detección de blancos y su umbral, comparación con los folios del FUID, cómo se reconoce el expediente y qué hallazgos se rechazan solos. Es versionado: cada archivo anota la versión que se le aplicó. `PUT/GET /proyectos/{id}/digitalizacion/perfil`. |
| Qué mide | Por archivo: legibilidad, formato, resolución (píxeles sobre el tamaño de página; **no se sube**, solo se mide), color, páginas sin imagen y páginas en blanco. Por expediente: partes o páginas que faltan, e imágenes contra folios del FUID. |
| Decisión automática | Sin hallazgos → **aprobado**. Con un hallazgo de rechazo automático → **rechazado**. Lo demás → **por revisar**. |
| Revisión humana | Aprobar a pesar de la alerta, o pedir recaptura, siempre con motivo. Quien cargó el archivo no aprueba sus propias alertas. Al llegar la recaptura, el archivo anterior queda **reemplazado** como evidencia. |
| Visor | Entrega el original solo después de verificar su huella. Si no coincide, lanza alerta de integridad. Ver el archivo también queda en la auditoría. |
| Pendiente | OCR local (D-21), PDF/A maestro y copia de consulta (M12). Detectar inclinación, recortes y duplicados visuales (no idénticos byte a byte). Carpeta vigilada en el servidor, para cargas sin navegador. |
