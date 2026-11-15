# Seguridad de las cuentas

Decisión D-46. Pruebas: `backend/tests/test_seguridad_cuentas.py` y `test_m02_usuarios.py`.

## Verificación en dos pasos obligatoria

Parámetro de la organización `seguridad.mfa_obligatorio` (Configuración, con motivo y versionado):

| Nivel | A quién se le exige |
|---|---|
| `ninguno` | A nadie (cada persona puede activarla) |
| `privilegiados` | A quien administra usuarios, roles o configuración |
| `direccion` | Además, a quien dirige proyectos, aprueba instrumentos o disposición, o ve lo reservado |
| `todos` | A todas las personas de la organización |

A quien se le exige y no la tiene, la API le responde 403 en todo lo de la organización; puede activarla en
**Mi cuenta**. La interfaz se lo dice y lo lleva allí. El parámetro anterior `seguridad.mfa_privilegiados` sigue
valiendo si no se ha publicado el nuevo.

## Correo saliente

`ARCA_SMTP_HOST`, `ARCA_SMTP_PUERTO`, `ARCA_SMTP_USUARIO`, `ARCA_SMTP_CLAVE`, `ARCA_SMTP_REMITENTE` (STARTTLS). Con
correo configurado:

- la **contraseña temporal** de una cuenta nueva o restablecida llega por correo y ya no se le muestra a quien
  administra;
- la persona puede **recuperar su contraseña** sola.

Sin correo, todo sigue como antes: la temporal se le muestra una vez al administrador.

## Recuperación de la contraseña

- `POST /auth/recuperar` responde lo mismo exista o no la cuenta. Envía un enlace de **un solo uso**, que vence a
  los 30 minutos (`ARCA_MINUTOS_RECUPERACION`). No reenvía en ráfaga: espera 2 minutos.
- ARCA guarda solo la huella del enlace, no el enlace.
- Al restablecer, se cierran las demás sesiones y se desbloquea la cuenta si el bloqueo fue por intentos
  fallidos. Un bloqueo puesto por el administrador no se levanta por correo.
- Queda en la auditoría: `SOLICITAR_RECUPERACION` y `RESTABLECER_CLAVE_POR_CORREO`.
