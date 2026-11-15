# Operación en servidor

Decisión D-45. Pruebas: `backend/tests/test_almacen.py` y `test_m03_m25_m28.py`. Archivos: `despliegue/`,
`backend/Dockerfile`, `frontend/Dockerfile`, `backend/scripts/prueba_carga.py`.

## Piezas

| Pieza | Qué es |
|---|---|
| `postgres` | PostgreSQL 16. Las pruebas automáticas también corren contra PostgreSQL (CI) |
| `migrar` | Aplica las migraciones (`alembic upgrade head`) antes de arrancar la API |
| `api` | La API (FastAPI), con Tesseract en español para el OCR |
| `trabajador` | La cola de trabajos (flujo automático y paquetes), en procesos aparte: `ARCA_TRABAJADORES` réplicas |
| `web` | La interfaz (Next.js); reenvía `/api` a la API, mismo origen |
| `caddy` | HTTPS automático (Let's Encrypt) para `ARCA_DOMINIO` |
| `minio` (perfil opcional) | Almacenamiento S3 propio, si no se usa el de una nube |

Puesta en marcha: `cd despliegue && cp .env.ejemplo .env` → completar el `.env` (los comandos para generar los
secretos están en el archivo) → `docker compose up -d --build`. Con MinIO: `docker compose --profile minio up -d`.

## Almacenamiento y cifrado

- **Proveedor:** `ARCA_ALMACEN_PROVEEDOR=local` (un volumen) o `s3` (AWS, MinIO o cualquiera compatible con S3).
  Los archivos se escriben una sola vez: en S3 con escritura condicional, no se sobrescriben.
- **Cifrado en reposo:** con `ARCA_CLAVE_CIFRADO_ALMACEN` (32 bytes en base64) cada archivo se guarda con
  AES-256-GCM, ligado a su clave de almacenamiento: alterarlo o moverlo de lugar se detecta. **En producción es
  obligatoria**: sin ella la aplicación no arranca. La huella SHA-256 sigue siendo la del original.
- **Cambio de llave:** la nueva en `ARCA_CLAVE_CIFRADO_ALMACEN` y la anterior en `ARCA_CLAVES_CIFRADO_ANTERIORES`.
- Los archivos guardados antes de activar el cifrado se siguen leyendo.
- **La llave se guarda fuera del servidor.** Sin ella no se pueden leer los archivos, ni desde una copia.

## Copias de seguridad

- `despliegue/copia_seguridad.sh /ruta`: la base de datos (`pg_dump`) y, si el almacén es local, sus archivos, con
  la huella de cada copia; conserva 30 días. Programarlo a diario.
- Con almacén S3, los archivos se protegen en el proveedor: versionado del bucket, replicación a otra región y, si
  el contrato lo pide, Object Lock.
- `despliegue/restaurar.sh /ruta marca`: comprueba las huellas de la copia y restaura. **Probar la restauración al
  menos una vez por trimestre** en un servidor aparte.

## Monitoreo

`GET /estado` (no se publica por Caddy; lo consulta el monitor desde la red interna) responde 503 si la base de
datos o el almacén no responden, y trae `alertas` en palabras:

- la cola tiene pendientes de más de 15 minutos (`ARCA_MINUTOS_ALERTA_COLA`), o sea, el trabajador está detenido;
- trabajos con error;
- poco espacio en el almacén local (`ARCA_GB_MINIMOS_LIBRES`, 20 GB);
- archivos que no se están cifrando en producción;
- OCR no instalado.

## Capacidad medida

`python scripts/prueba_carga.py --paginas 40 --procesos N` mide en el servidor real, con páginas ficticias A4 a
300 ppp. En el servidor de desarrollo (4 núcleos) dio:

| Etapa | Segundos de un núcleo por página |
|---|---|
| Recepción (calidad, huella, almacén cifrado) | 0,03 |
| OCR con detección de orientación | 1,50 |
| PDF/A con capa de texto (paquete de entrega) | 0,76 |
| **Total** | **2,30** |

Con 4 procesos: unas 5.800 páginas por hora, 138.700 por día de 24 horas. **Para 500.000 páginas diarias harían
falta unos 14 núcleos dedicados** al trabajador, más la base de datos y la interfaz. Las páginas reales escaneadas
(con ruido, sellos, manuscritos) pueden tardar más: hay que medir con una muestra del proyecto.

`ARCA_HILOS_OCR=1` (por defecto): un hilo por proceso de Tesseract. Con varios trabajadores, más hilos por
proceso saturan los núcleos (en la medición, una página pasó de 1,5 s a más de 180 s).

## Validado en el entorno de desarrollo

- Las imágenes de la API y de la interfaz se construyeron y arrancaron.
- La API corrió en modo producción contra PostgreSQL 16 en contenedor, con las 22 migraciones y el almacén
  cifrado, y `/estado` respondió con sus alertas.
- No se pudo instalar Tesseract dentro de la imagen en este entorno: su red bloquea los repositorios de Debian. En un
  servidor con salida normal a internet se instala con el `Dockerfile` tal como está.
