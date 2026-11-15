# ARCA

Plataforma SaaS multiempresa de gestión archivística, digitalización masiva, automatización documental
y preservación digital, para entidades públicas, empresas privadas y consultoras.

Es un sistema **independiente**. Recicla, copiado y adaptado, código probado de dos plataformas
anteriores: Kustos (SGDEA) y GEOLOGY (organización y descripción de fondos acumulados con IA).

**Principio:** la IA asiste y propone. Las decisiones archivísticas críticas exigen evidencia,
autorización y trazabilidad.

## Estado

| Etapa | Módulos | Estado |
|---|---|---|
| 0 · Preparación | Decisiones, alcance y reciclaje | En curso: [`docs/00_DECISIONES.md`](docs/00_DECISIONES.md) y [`docs/01_ALCANCE_Y_RECICLAJE.md`](docs/01_ALCANCE_Y_RECICLAJE.md) |
| **1 · Plataforma base** | M01 organizaciones, M02 usuarios, roles y MFA, M03 parámetros con vigencia, M06 proyectos, M25 auditoría, M28 estado | **Construida.** Fichas: [`docs/fichas/ETAPA_1_PLATAFORMA_BASE.md`](docs/fichas/ETAPA_1_PLATAFORMA_BASE.md) |
| **Pantallas** | Ingreso con verificación en dos pasos, Inicio, Proyectos, Usuarios, Roles, Configuración, Auditoría, Mi cuenta y Organizaciones (operador) | **Construidas** sobre el diseño de Kustos y RICORA |
| **Incremento 2A** | M08 inventario FUID, M10 carga desde carpeta (PDF por expediente e imágenes por página), M11 control de calidad con perfil configurable y bandeja de revisión | **Construido.** Ficha: [`docs/fichas/INCREMENTO_2A_INVENTARIO_DIGITALIZACION.md`](docs/fichas/INCREMENTO_2A_INVENTARIO_DIGITALIZACION.md) |
| **M24 Productividad** | Tablero en tiempo real con el diseño de Power BI, base de cajas (procesadas y pendientes), registro diario, conteo automático y llaves de lectura para Power BI | **Construido.** Ficha: [`docs/fichas/M24_PRODUCTIVIDAD_POWER_BI.md`](docs/fichas/M24_PRODUCTIVIDAD_POWER_BI.md) |
| **Entregables** | Plantillas de la entidad versionadas (FUID de salida, rótulos de caja y de carpeta) y expedición con evidencia | **Construido.** Ficha: [`docs/fichas/ENTREGABLES_PLANTILLAS.md`](docs/fichas/ENTREGABLES_PLANTILLAS.md) |
| **M04 Instrumentos** | TRD, TVD y CCD del proyecto: importación tolerante (tabular o formato AGN), validación sin inventar datos, aprobación segregada con acto administrativo, versiones programadas o reemplazadas y comparación entre versiones. Clasificación de las unidades del FUID (automática por código, propuesta por nombre, asignación por lotes) con calendario de retención | **Construido.** Ficha: [`docs/fichas/M04_INSTRUMENTOS_TRD_TVD_CCD.md`](docs/fichas/M04_INSTRUMENTOS_TRD_TVD_CCD.md) |
| **Transferencias** | Ciclo vital por unidad (gestión, central, histórico), plan a la fecha de corte, transferencias primaria y secundaria con recepción por unidad y segregación, fase de partida para fondos acumulados e inventario en el FUID de la entidad | **Construido.** Ficha: [`docs/fichas/TRANSFERENCIAS_DOCUMENTALES.md`](docs/fichas/TRANSFERENCIAS_DOCUMENTALES.md) |
| **Disposición final** | Eliminación con comité, publicación y acta en el formato de la entidad; selección por muestreo reproducible; digitalización verificada contra lo digitalizado; todo queda como evidencia | **Construido.** Ficha: [`docs/fichas/DISPOSICION_FINAL.md`](docs/fichas/DISPOSICION_FINAL.md) |
| **Hoja de control** | Elaboración sobre lo digitalizado (partir por páginas, folios calculados), visor de cada página, origen de cada dato, importación de hojas en Excel, verificación trámite por trámite por otra persona y expedición en el formato de la entidad | **Construido.** Ficha: [`docs/fichas/HOJA_DE_CONTROL.md`](docs/fichas/HOJA_DE_CONTROL.md) |
| **M13 OCR local** | Tesseract en el servidor, lectura por tandas, texto por página con su confianza, búsqueda en el contenido y propuesta de la hoja de control (corte de documentos, tipo, fecha, detalle, radicado) para confirmar | **Construido.** Ficha: [`docs/fichas/M13_OCR.md`](docs/fichas/M13_OCR.md) |
| **Descripción ISAD(G)** | Procesos por lote (hoja de control, ISAD(G) o ambas), descripción sobre lo digitalizado con el origen de cada elemento, revisión según la norma, aprobación por otra persona y base de descripción en el formato de la entidad | **Construido.** Ficha: [`docs/fichas/DESCRIPCION_ISADG.md`](docs/fichas/DESCRIPCION_ISADG.md) |
| **M23 Consulta** | Búsqueda sin tildes en metadatos, OCR, hoja verificada y descripción aprobada, con filtros, fragmentos y exportación; ficha del expediente con visor; acceso según la TRD y alcance por proyecto (también para la entidad cliente) | **Construido.** Ficha: [`docs/fichas/M23_CONSULTA.md`](docs/fichas/M23_CONSULTA.md) |
| **Flujo automático** | Al cargar, calidad → OCR → hoja de control → descripción sin intervención, hasta donde decide una persona; cola de trabajos en la base de datos con trabajador en la aplicación o aparte; tablero por etapa | **Construido.** Ficha: [`docs/fichas/FLUJO_AUTOMATICO.md`](docs/fichas/FLUJO_AUTOMATICO.md) |
| **Automatización y paquete de entrega** | Metadatos de cada documento desde el OCR (asunto, remitente, destinatario, firmantes, lugar), páginas giradas enderezadas, avisos de legibilidad, FUID con folios contados, productividad contada sola y paquete digital para el SGDEA (PDF/A-2b validado con texto buscable, metadatos, hoja y manifiesto de huellas); validador PDF/A para cualquier PDF | **Construido.** Ficha: [`docs/fichas/AUTOMATIZACION_Y_PAQUETE_DE_ENTREGA.md`](docs/fichas/AUTOMATIZACION_Y_PAQUETE_DE_ENTREGA.md) |
| **Historias laborales** | Titular de cada expediente propuesto desde el FUID o el OCR y confirmado por una persona; páginas con el número de documento de otra persona, tipos documentales mínimos que faltan, orden cronológico y titulares repetidos; búsqueda por número de documento | **Construido.** Ficha: [`docs/fichas/HISTORIAS_LABORALES.md`](docs/fichas/HISTORIAS_LABORALES.md) |
| **Inspección de calidad por lote** | Plan de muestreo de la dirección, muestra al azar con semilla registrada, defectos por severidad, aceptación o rechazo calculados según el plan, reinspección, acta y registro de calidad para el tablero; el paquete de entrega puede exigir lotes aceptados | **Construido.** Ficha: [`docs/fichas/INSPECCION_CALIDAD_POR_LOTE.md`](docs/fichas/INSPECCION_CALIDAD_POR_LOTE.md) |
| Siguiente | Validación externa con veraPDF, documentos expedidos en PDF con logos, despliegue en servidor (PostgreSQL, almacenamiento S3, cifrado) | Pendiente |

Hay 155 pruebas automáticas en el backend. La meta de 500.000 imágenes diarias es un objetivo de diseño. No es una capacidad demostrada.

## Probarlo en local

Requiere Python 3.12 o superior y Node.js 20 o superior. Son dos procesos: la API (puerto 8000) y la
interfaz (puerto 3000). La interfaz reenvía `/api/*` a la API, así que el navegador solo habla con el
puerto 3000.

**1. API**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
sudo apt-get install tesseract-ocr tesseract-ocr-spa     # OCR local (opcional; sin él, el OCR se informa como no disponible)
python -m pytest -q                                    # pruebas
alembic upgrade head                                   # crea la base (SQLite local por defecto)
python scripts/crear_operador.py operador@suempresa.com "Nombre Apellido"
uvicorn arca.main:app --reload                         # en local trae el trabajador del flujo automático
# En producción, el trabajador va aparte:  python -m arca.modulos.flujo.trabajador
```

**2. Interfaz** (en otra terminal)

```bash
cd frontend
npm install
npm run dev
```

Abra <http://localhost:3000> e ingrese con el operador que creó. La primera vez le pide cambiar la
contraseña temporal. Desde **Organizaciones** cree la primera organización; su administrador entra
por la misma pantalla.

- Documentación interactiva de la API: <http://localhost:8000/docs>
- Estado del servicio: <http://localhost:8000/estado>

Para usar PostgreSQL, defina `ARCA_DATABASE_URL=postgresql+psycopg://usuario:clave@servidor:5432/arca`.
Fuera de local y pruebas son obligatorias `ARCA_CLAVE_SECRETA` y `ARCA_CLAVE_SELLADO`, y deben ser
distintas (ver `.env.example`).

## Recorrido mínimo por la API

1. El operador ingresa (`POST /api/v1/auth/ingresar`) y cambia su contraseña temporal (`/auth/cambiar-clave`).
2. Crea una organización (`POST /api/v1/plataforma/organizaciones`) con su administrador inicial.
3. El administrador ingresa y, enviando la cabecera `X-Organizacion: <id>`, agrega usuarios
   (`/usuarios`), crea un proyecto (`/proyectos`), le pone sede y metas, y lo activa.
4. Todo queda en `/api/v1/auditoria/eventos`, y `/api/v1/auditoria/verificar` comprueba que la
   cadena esté íntegra.

## Estructura

```
backend/
  arca/
    nucleo/       configuración, base de datos, errores, seguridad (Argon2, JWT, TOTP, NIT), permisos
    modelos/      tablas: plataforma (organización, usuario, rol, membresía), operación (proyecto,
                  versión, sede, equipo, parámetro), auditoría (eventos, cadenas, sellos)
    api/deps.py   sesión, organización activa, alcance por proyecto y permisos (denegar por defecto)
    modulos/mNN_* un módulo por carpeta: servicios.py (reglas) y rutas.py (API)
  alembic/        migraciones (la 0001 crea la Etapa 1 y protege la auditoría en PostgreSQL)
  tests/          pruebas por módulo, más aislamiento entre organizaciones y migraciones
  scripts/        crear_operador.py
frontend/
  src/app/        pantallas: ingresar, elegir organización y (app)/ con inicio, proyectos, usuarios,
                  roles, configuración, auditoría, cuenta y plataforma
  src/components/ sistema de diseño reutilizado de Kustos (basicos, campos, avisos) y la barra de ARCA
  src/lib/        cliente de la API, sesión, permisos, tipos
docs/             decisiones, alcance y reciclaje, fichas de módulo
```

## Reglas de trabajo (Instrucciones de desarrollo v1)

- Se construye por incrementos verticales. Ningún componente se declara terminado sin pruebas.
- Las decisiones no definidas se registran como pendientes; no se inventan.
- Solo se usan datos ficticios o anonimizados.
- Ningún módulo modifica otro sin documentar la dependencia.
