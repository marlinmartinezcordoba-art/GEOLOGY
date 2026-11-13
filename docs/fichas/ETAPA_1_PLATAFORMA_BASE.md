# Etapa 1 · Plataforma base: fichas de módulo

Fichas según el §3 de las Instrucciones v1, con lo que **quedó construido**. Cada criterio de
aceptación remite a la prueba automática que lo demuestra (carpeta `backend/tests/`).

Transversal a todos los módulos:
- Toda ruta, salvo `/estado` y el ingreso, exige sesión. Toda ruta con datos de cliente exige además
  membresía activa en la organización activa (cabecera `X-Organizacion`).
- Un registro de otra organización responde **404**, para no revelar siquiera que existe.
- Cada cambio queda en la auditoría con actor, fecha, valores anterior y nuevo, motivo, IP e
  identificador de correlación (cabecera `X-Correlation-ID`, que viaja a la respuesta).
- Nada se borra: se suspende, se desactiva o se cierra, siempre con motivo.

---

## M01 · Administración de organizaciones y tenants

| Campo | Contenido |
|---|---|
| Objetivo | Crear organizaciones cliente y garantizar el aislamiento SaaS. |
| Actores | **Operador de la plataforma** (`es_operador`): crea, edita, suspende y reactiva. No tiene membresías y por eso no ve el contenido de las organizaciones. El **administrador de la organización** consulta el perfil. |
| Pantallas y API | `POST/GET /api/v1/plataforma/organizaciones`, `GET/PATCH …/{id}`, `POST …/{id}/suspender`, `POST …/{id}/reactivar`, `GET /api/v1/plataforma/auditoria/verificar`, `GET /api/v1/organizacion` (perfil y consumo). |
| Flujo principal | Registrar datos → validar el NIT y su dígito de verificación (DIAN) → crear el tenant → zona horaria, idioma y límites → sembrar los 5 roles base → asignar el administrador inicial (cuenta nueva con contraseña temporal de un solo uso, o una cuenta existente) → activa. |
| Alternos y excepciones | NIT inválido o repetido: 422 o 409. Suspender o reactivar sin motivo: 422. Suspender una organización ya suspendida: 422. Al alcanzar el límite de usuarios o proyectos: 409. Un límite que aún no se hace cumplir: 422. |
| Reglas | Una organización nunca consulta datos de otra. Si está suspendida, sus usuarios no entran, pero se conservan sus datos y su auditoría. |
| IA | Ninguna (la IA no autoriza accesos). |
| Auditoría | El evento queda doble: en la cadena de la plataforma y en la de la organización. |
| Aceptación | `test_aislamiento.py` (cabecera ajena, identificadores ajenos, listados, roles, usuarios, auditoría y configuración), `test_m01_organizaciones.py`. |
| Pendiente | Acceso excepcional del operador (D-09). Aislamiento de archivos, búsqueda, caché y vectores: se prueba cuando existan esas capas. |

## M02 · Usuarios, roles y permisos

| Campo | Contenido |
|---|---|
| Objetivo | Identidad, autenticación y autorización. |
| Actores | Cualquier usuario (ingreso, su cuenta y MFA). El administrador de la organización (usuarios). Quien tenga `roles:gestionar` (roles). |
| API | `POST /auth/ingresar` · `POST /auth/token` (formulario para `/docs`) · `GET /auth/yo` · `POST /auth/cambiar-clave` · `POST /auth/cerrar-sesiones` · `POST /auth/mfa/iniciar` · `POST /auth/mfa/confirmar` · `GET/POST /usuarios` · `PATCH /usuarios/{id}` (rol y alcance) · `POST /usuarios/{id}/desactivar`, `/reactivar`, `/revocar-sesiones`, `/restablecer-clave` · `GET/POST /roles` · `PATCH /roles/{id}` · `GET /roles/permisos`. |
| Flujo principal | Agregar usuario → rol → alcance (todos los proyectos o algunos) → contraseña temporal → primer ingreso obliga a cambiarla → (opcional u obligatoria por política) activar MFA. |
| Reglas | Se deniega por defecto. El ingreso no revela si el correo existe. Bloqueo tras 5 intentos. La sesión se invalida al cambiar la clave, activar MFA, revocar o bloquear. **Segregación:** nadie cambia su propio acceso ni edita el rol que tiene, y la organización nunca se queda sin administrador. Los roles base no se editan. Solo se aceptan permisos existentes. Restablecer la clave de alguien que pertenece a otras organizaciones le corresponde al operador. |
| MFA | TOTP (RFC 6238), compatible con las aplicaciones autenticadoras comunes. Con `seguridad.mfa_privilegiados = true`, los roles que administran usuarios, roles o configuración no operan sin MFA. |
| Aceptación | `test_m02_usuarios.py`: cada rol, revocación, desactivación, bloqueo, MFA y política MFA. |
| Pendiente | Matriz de roles aprobada (D-07). Cifrado del secreto MFA (D-11). Invitación por correo, que hoy se resuelve entregando la contraseña temporal. |

## M03 · Configuración institucional

| Campo | Contenido |
|---|---|
| Objetivo | Parámetros por organización o por proyecto, versionados y con vigencia. |
| API | `GET /configuracion/parametros?proyecto_id=&fecha=` · `GET /configuracion/parametros/{clave}/historial` · `POST /configuracion/parametros` · `GET /configuracion/parametros/conocidos`. |
| Reglas | Una versión publicada no se edita: se publica otra. **La vigencia no puede ser pasada**, para no cambiar lo que ya ocurrió. El parámetro de proyecto prevalece sobre el de la organización. Se puede consultar lo que regía en cualquier fecha. |
| Aceptación | `test_m03_m25_m28.py`: vigencia futura, no retroactividad, prevalencia por proyecto y validación de claves y valores. |
| Pendiente | Catálogos institucionales y plantillas: llegan con M04 y M08. |

## M06 · Proyectos, contratos y órdenes de trabajo

| Campo | Contenido |
|---|---|
| Objetivo | Organizar la operación por contrato, proyecto, sede, metas y equipo. |
| API | `GET/POST /proyectos` · `GET/PATCH /proyectos/{id}` · `POST …/activar`, `/cerrar`, `/reabrir` · `GET …/versiones` · `GET/POST …/sedes` · `GET/POST …/equipo`. |
| Estados | `borrador → activo → cerrado → (reabrir con motivo) activo`. |
| Reglas | El código es único dentro de la organización. **El alcance se versiona** con una instantánea y un motivo por cada cambio. Para activar el proyecto se exigen fechas, al menos una meta, un responsable y al menos una sede. Un proyecto activo no puede quedar sin metas. Uno cerrado no se edita. Las metas van por unidad y no se mezclan. El responsable y el equipo deben ser miembros activos y estar dentro de su alcance. |
| Aceptación | `test_m06_proyectos.py`. |
| Pendiente | Turnos y la comparación de metas contra avance real, que llega con M24 cuando haya eventos operativos. |

## M25 · Auditoría y trazabilidad (parcial)

| Campo | Contenido |
|---|---|
| API | `GET /auditoria/eventos` (filtros por acción, objeto, objeto_id y correlación; paginación) · `GET /auditoria/verificar`. Consultar y verificar también quedan auditados. |
| Protección | Una cadena SHA-256 por organización y un sello HMAC periódico con una clave aparte, que detecta incluso la reescritura completa de la tabla. En PostgreSQL, disparadores impiden `UPDATE` y `DELETE` sobre la auditoría. |
| Aceptación | `test_m03_m25_m28.py`: cadena íntegra, evento alterado, último evento borrado y reescritura con huellas recalculadas detectada por el sello. |
| Pendiente | Alertas, investigaciones y exportación verificable. |

## M28 · Operación (base)

`GET /estado` informa servicio, versión, entorno, hora UTC y disponibilidad de la base de datos, y
responde 503 si la base no está disponible. Toda petición lleva su identificador de correlación.
