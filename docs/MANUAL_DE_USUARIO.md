# ARCA · Manual de usuario por rol

Este manual dice qué hace cada persona en ARCA durante un proyecto de digitalización masiva y organización de
historias laborales, y en qué pantalla lo hace. Las pantallas del proyecto son pestañas: se abren desde
**Proyectos → el proyecto**.

Reglas que valen para todos:

- **ARCA propone y una persona decide.** Lo que ARCA calcula o propone (desde el FUID, la TRD o el OCR) dice de
  dónde salió. Nada propuesto pasa a un entregable sin que alguien lo confirme.
- **Quien elabora no verifica.** El sistema no deja que la misma persona elabore y verifique una hoja de control,
  ni que inspeccione archivos que ella misma cargó.
- **Todo queda en la auditoría,** con quién, cuándo y por qué. Las decisiones piden motivo.

## Primer ingreso y seguridad de la cuenta

1. **Primer ingreso.** Entre con su correo y la contraseña temporal que le llegó por correo (o que le entregó el
   administrador). ARCA le pide crear una propia, de al menos 12 caracteres.
2. **Olvidó la contraseña.** En la pantalla de ingreso, **¿Olvidó su contraseña?** → escriba su correo → abra el
   enlace que le llega (vale 30 minutos y una sola vez). Si no le llega, pídale al administrador que la restablezca.
3. **Verificación en dos pasos.** En **Mi cuenta → Verificación en dos pasos**, escanee el código con una aplicación
   de autenticación y confirme con el código de 6 dígitos. Si su organización la exige para su rol, ARCA no le deja
   entrar a las secciones hasta que la active.
4. **Cinco intentos fallidos** bloquean la cuenta. La recuperación por correo la desbloquea; un bloqueo puesto por
   el administrador, no.

## Administración de la organización

| Qué hace | Dónde |
|---|---|
| Crear usuarios y asignarles rol y proyectos | **Usuarios → Agregar persona** (la contraseña temporal sale por correo si hay correo configurado) |
| Restablecer la contraseña, bloquear o cerrar las sesiones de alguien | **Usuarios →** la persona |
| Exigir verificación en dos pasos | **Configuración →** parámetro `seguridad.mfa_obligatorio`: `ninguno`, `privilegiados`, `direccion` o `todos` |
| Subir las plantillas de la entidad (FUID, rótulos, hoja de control, lista de chequeo…) | **Plantillas** |
| Revisar la auditoría y verificar su cadena | **Auditoría → Verificar** |

## Dirección de proyecto

| Qué hace | Dónde |
|---|---|
| Alcance, fechas, metas, sedes y equipo; activar el proyecto | Pestañas **Resumen, Sedes, Equipo** y **Editar alcance** |
| Cargar y aprobar la TRD con su acto administrativo | **TRD · TVD · CCD** |
| Configurar historias laborales: series, tipos documentales mínimos (BANTER y TRD), acceso restringido | **Historias laborales → Configuración del proyecto** |
| Fijar las actividades de alistamiento | **Alistamiento físico → Actividades de alistamiento** |
| Fijar el perfil de digitalización (formatos, resolución, color, rechazo automático) | **Digitalización y calidad → Perfil** |
| Fijar el plan de muestreo de la inspección por lote | **Calidad por lote → Plan de muestreo** |
| Verificar las hojas de control trámite por trámite | **Hoja de control →** el expediente → **Verificar** |
| Anular una inspección abierta (con motivo) | **Calidad por lote →** la inspección |
| Configurar el archivo de indexación del SGDEA | **Entregables → Archivo de indexación para el SGDEA** |
| Subir el logo de la entidad | **Entregables → Logo de la entidad** |
| Sacar el informe de avance para la interventoría | **Entregables → Informe de avance** (PDF/A o Excel) |
| Pedir el paquete de entrega | **Entregables → Paquete de entrega digital** |

## Equipo operativo

**En la bodega (antes de digitalizar):**

1. **Diagnóstico de conservación.** En **Alistamiento físico**, abra la caja y, en cada expediente, **Diagnosticar**:
   estado (bueno, regular, malo) y hallazgos. Si hay deterioro biológico, ARCA marca el expediente **para aislar**.
2. **Alistamiento.** En la caja, **Registrar**: elija la actividad (depuración, ordenación cronológica, foliación,
   retiro de material abrasivo, cambio de carpeta, rotulación…) y marque los expedientes. En la foliación escriba
   los folios contados (ARCA sugiere los del FUID). Si se equivocó, **deshacer** pide motivo.

**En digitalización:**

3. **Cargar lo digitalizado.** En **Digitalización y calidad**, cargue la carpeta: ARCA reconoce a qué expediente
   va cada archivo, le saca la huella y revisa la calidad. Lo dudoso queda en revisión.
4. **Decidir la calidad.** Apruebe o pida recaptura de lo que quedó en revisión, con motivo.

**Después, ARCA avanza sola** (pestaña **Flujo automático**): lee con OCR, endereza las páginas, propone la hoja de
control y, en historias laborales, el titular. El tablero dice dónde espera a una persona.

5. **Confirmar la hoja de control.** En **Hoja de control →** el expediente: revise cada documento propuesto (corte,
   tipo, fecha, folios, asunto, remitente…), corrija lo necesario, **confirme** y **envíe a verificación**. Otra
   persona la verifica.
6. **Confirmar el titular.** En **Historias laborales**: revise las alertas (documentos de otra persona, titular
   repetido, tipos mínimos que faltan), confirme el titular y complete cargo, dependencia y fechas de vinculación y
   retiro. La fecha de retiro cuenta para la retención.
7. **Inspeccionar un lote** (quien no cargó esos archivos). En **Calidad por lote → Inspeccionar**: revise cada
   elemento de la muestra, marque sus defectos o «sin defectos» y **cierre**. ARCA acepta o rechaza el lote según el
   plan; un lote rechazado se corrige y se reinspecciona.
8. **Expedir la lista de chequeo** de cada historia: **Historias laborales → Lista de chequeo**.

## Consulta y auditoría

| Qué hace | Dónde |
|---|---|
| Buscar expedientes (por número de documento, nombre, texto del OCR, metadatos) | **Consulta** |
| Ver la auditoría y verificar que la cadena está íntegra | **Auditoría** |
| Ver tableros e informes | Pestaña **Productividad** del proyecto; **Entregables → Informe de avance** |

Las historias laborales son de acceso restringido: sin el permiso de consulta reservada, la consulta muestra los
metadatos pero no el texto ni las imágenes.

## Entidad cliente

Consulta su proyecto: el avance (**Productividad**), la consulta de expedientes según su permiso y el informe de
avance. No ve otros proyectos.

## Si algo no funciona

- El **tablero del flujo** muestra los trabajos con error y permite reintentarlos.
- El estado del servicio (`/estado`, para quien opera el servidor) dice si la base de datos, el almacén y el OCR
  responden, y lista las alertas: cola detenida, poco espacio, archivos sin cifrar.
- Reporte la falla con el **identificador de correlación** que muestra el mensaje de error.
