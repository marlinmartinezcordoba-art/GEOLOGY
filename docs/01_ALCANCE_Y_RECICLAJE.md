# ARCA · Módulos, etapas y código que se recicla

**ARCA no es un SGDEA (D-38).** Es un sistema de automatización aparte: digitalización, calidad, hoja de control y
extracción de metadatos, con lo archivístico justo para esos proyectos. Lo que es propio de un SGDEA queda fuera.

Se usan los módulos **M01 a M28** de las *Instrucciones de desarrollo asistido por IA v1*, con su
equivalencia en el *Documento Maestro v1.8* (ARC-01 a ARC-28).

**Reciclar** significa copiar el código fuente a ARCA y adaptarlo: quitar lo específico de cada cliente
y agregar `tenant_id`, auditoría y versionado. ARCA no depende de Kustos ni de GEOLOGY en ejecución.

## Estado por módulo

| M | Módulo | ARC | Etapa | Fuente que se recicla | Estado |
|---|--------|-----|-------|-----------------------|--------|
| M01 | Organizaciones y tenants | ARC-01, ARC-27 parcial | 1 | Kustos: multientidad, cuotas | **Construido** |
| M02 | Usuarios, roles y permisos | ARC-03 | 1 | Kustos: `api/deps.py`, `security/` · GEOLOGY: perfiles | **Construido** |
| M03 | Configuración institucional | ARC-28 | 1 | Kustos: `organizacion/configuracion.py` | **Construido** (parámetros con vigencia) |
| M06 | Proyectos, contratos y órdenes | ARC-02 | 1 | GEOLOGY: equipo y funciones por contrato | **Construido** |
| M25 | Auditoría y cumplimiento | ARC-25 | 1 (parcial) | Kustos: `comun/servicios/auditoria.py` (cadena SHA-256 y sellos HMAC) | **Construido**: bitácora, consulta y verificación. Pendientes: alertas e investigaciones |
| M28 | Operación y monitoreo | — | 1 (base) | — | **Construido**: `/estado` y correlación de peticiones |
| M04 | Instrumentos (CCD, TRD, TVD) | ARC-05 | 2 | Kustos: `instrumentos/importar_trd.py`, `versiones.py` · GEOLOGY: `dominio/clasificacion.py`, `periodos.py` (TVD por periodo **y dependencia**), `scripts/revisar_tvd.py` | **Construido**: TRD, TVD y CCD versionadas, clasificación y calendario de retención |
| M07 | Recepción física y unidades | ARC-06, ARC-07 | 2 | Kustos: `expedientes/archivo_fisico.py`, `gemelo_deposito.py` · GEOLOGY: `dominio/cajas.py` | Pendiente |
| M08 | Inventarios y FUID | ARC-07 | 2 | Kustos: `expedientes/importar_fuid.py` · GEOLOGY: `importar_hoja.py`, `verificar_hoja.py`, `hojas_calculo.py`, `codigos.py`, `folios.py` | **Construido**: FUID, base de cajas y hoja de control (importación, folios, verificación) |
| M17 | Expediente electrónico | ARC-15, ARC-17 | 2 | Kustos: `expedientes/` (ciclo, índice, hoja de cierre en PDF/A) | **Fuera del alcance como SGDEA (D-38).** Se reemplaza por el paquete de entrega digital por expediente (PDF/A, índice y metadatos) para cargar en el SGDEA de la entidad |
| M09 | Alistamiento | ARC-08 | 3 | — | Pendiente |
| M10 | Captura y digitalización | ARC-08 | 3 | Kustos: `captura/digitalizacion.py` · GEOLOGY: cargue por partes (`rutas/cargue.py`) | **Construido**: carga desde carpeta (2A) |
| M11 | Control de calidad de imágenes | ARC-09 | 3 | Kustos: `captura/calidad_automatica.py` · GEOLOGY: `dominio/recepcion_tecnica.py` | **Construido**: perfil configurable y bandeja de revisión |
| M12 | Procesamiento y normalización | ARC-10 | 3 | Kustos: `captura/procesamiento.py` · GEOLOGY: `division.py`, `particion.py` (libros por partes) | Pendiente |
| M13 | OCR y HTR | ARC-11 | 4 | Kustos: `captura/ocr.py` · GEOLOGY: OCRmyPDF y Tesseract en `trabajos/` | **Construido**: OCR local (Tesseract) y propuesta de la hoja de control. Pendiente: HTR |
| M14 | Segmentación documental | ARC-13 | 4 | GEOLOGY: hoja de control con IA (trámites con rangos de folios) en `lectores.py` e `instrucciones.py` | **Parcial**: corte de documentos por reglas sobre el OCR. Pendiente: con IA |
| M15 | Clasificación asistida | ARC-12 | 4 | GEOLOGY: `clasificacion.py`, `tipologias.py` · Kustos: `clasificacion/` | Pendiente |
| M16 | Extracción de metadatos | ARC-14 | 4 | GEOLOGY: `fechas.py`, `descripcion_isad.py`, `revision_isadg.py` · Kustos: `metadatos/` | **Parcial**: fechas, tipo y radicado desde el OCR; descripción ISAD(G) por expediente. Pendiente: con IA |
| M27 | IA, modelos y RAG | ARC-21, ARC-22 | 4 | GEOLOGY: `lectores.py`, `catalogo.py` (varios proveedores, cuotas, y nunca inventa) · Kustos: `ia/proveedores.py`, `minimizacion.py` | Pendiente |
| M18 | BPM y tareas (incluye revisión humana) | ARC-16, ARC-23 | 5 | GEOLOGY: `dominio/estados.py` (ciclo con revisión y aprobación) · Kustos: `tramites/` | **Parcial**: revisión por otra persona en calidad, TRD, clasificación, hoja, descripción, transferencias y disposición. Pendiente: asignación de tareas |
| M20 | Transferencias | ARC-19 | 5 | Kustos: `retencion/` | **Construido**: primaria y secundaria, fase de partida |
| M22 | Preservación digital | ARC-20 | 5 | Kustos: `preservacion/` (PREMIS, identificación de formatos) | Pendiente |
| M23 | Búsqueda y recuperación | ARC-21 parcial | 5 | Kustos: `consulta/` · GEOLOGY: `rutas/consulta.py` (consulta de la entidad) | **Construido**: búsqueda, ficha, acceso según la TRD y entidad cliente |
| M24 | Reportes y tableros | ARC-04, ARC-26 | 5 | GEOLOGY: `dominio/produccion.py` (producción diaria calculada de la bitácora) · Kustos: `consulta/tablero.py` | **Construido**: tablero de productividad, base de cajas y Power BI |
| M05 | Recepción y ventanilla única | ARC-06 parcial | 6 | Kustos: `radicacion/` | **Fuera del alcance (D-38)**: la radicación es del SGDEA |
| M19 | Firma y aprobaciones | — | 6 | Kustos: `firma/` (PAdES) | **Fuera del alcance (D-38)**: las aprobaciones quedan con su persona y su auditoría; la firma es del SGDEA |
| M21 | Disposición final | ARC-19 | 6 | Kustos: `disposicion/` (doble autorización) | **Construido**: eliminación, selección y digitalización |
| M26 | Integraciones | ARC-24 | 6 | Kustos: `integraciones/` | **Solo exportación (D-38)**: paquete de entrega, Excel y Power BI; sin integraciones en línea con el SGDEA |
| — | Entregables | ARC-18 | 2 a 5 | GEOLOGY: el llenado de plantillas oficiales del cliente, convertido en plantillas configurables por proyecto | **Construido**: FUID, rótulos, actas de eliminación, hoja de control y base ISAD(G) en plantillas de la entidad |

## Lo que NO se recicla

- Los formatos, la tabla de valoración, los periodos institucionales y la numeración de cajas del cliente
  del contrato para el que se construyó GEOLOGY. En
  ARCA cada proyecto sube sus propias plantillas e instrumentos.
- Los datos de GEOLOGY: inventarios, bitácoras y documentos (ver D-17).
- Lo que en Kustos es propio de un SGDEA para entidades públicas y no forma parte del alcance de
  ARCA en esta fase: PQRSD, portal ciudadano y transparencia.
