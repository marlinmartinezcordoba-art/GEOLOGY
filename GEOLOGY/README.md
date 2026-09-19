# GEOLOGY

Plataforma de organización y descripción documental del fondo acumulado del Servicio
Geológico Colombiano. Contrato 733 de 2026 · Hometic SAS.

Recibe los expedientes digitalizados del inventario de origen, levanta y verifica la hoja de
control (F-GDM-007 v4), genera y valida la descripción ISAD(G), asigna caja definitiva y expide
el inventario de salida F-GDM-003 v9 (FUID) con los rótulos F-GDM-006 y F-GDM-008. La entidad
contratante consulta lo publicado desde su propio perfil.

## Arranque en tres pasos

```bash
copy .env.example .env          # Windows  (Linux/Mac: cp .env.example .env)
# escriba en .env la clave de PostgreSQL, GEOLOGY_CLAVE y las llaves de los lectores
docker compose up -d --build
```

Después, una sola vez:

```bash
docker compose exec servidor python scripts/cargar_inventario.py      # inventario de origen y tablas de valoración
docker compose exec servidor python scripts/cargar_contexto.py        # contexto de los periodos institucionales
copy datos\equipo.ejemplo.csv datos\equipo.csv                        # escriba el equipo y las cuentas de la entidad
docker compose exec servidor python scripts/crear_usuarios.py         # imprime las claves provisionales
docker compose exec procesador python scripts/revisar_motor.py        # comprueba llaves, depósito y motor de imagen
```

Abra `http://localhost:8080/app`. Estado del sistema: `http://localhost:8080/estado`.

Todo lo demás está en `docs/DESPLIEGUE.md` (instalación en servidor, migración desde la
plataforma anterior, respaldo, resolución de problemas) y en `docs/MANUAL.md` (cómo se usa).

## Estructura

```
geology/
  nucleo/       ajustes (.env), bd, cola de trabajos, estructura de tablas, pases de sesión
  modelos/      tablas: unidad_documental, asiento_hoja, inventario_origen, archivo_digital,
                caja_definitiva, cuenta, bitacora, consumo_lector, periodo/seccion/serie/subserie
  dominio/      reglas: códigos, estados, verificación de hojas, descripción ISAD(G), formatos
                oficiales, división de documentos, cajas, expedición, lectores
  rutas/        API: /cargue /unidades /ubicacion /instrumentos /cuentas /consulta
  trabajos/     tareas en segundo plano (lectura, recepción técnica)
  interfaz/     la interfaz web (un solo archivo)
scripts/        carga de datos, cuentas, pruebas, migración, mantenimiento
datos/          inventario de origen, tablas de valoración, plantillas oficiales
deposito/       documentos digitalizados (no se versiona)
expedidos/      instrumentos expedidos (no se versiona)
```

## Requisitos del servidor

Docker y Docker Compose. Nada más: PostgreSQL 15, Redis 7, Python 3.11 y el motor de imagen
(Tesseract, Ghostscript, qpdf, unpaper) van dentro de los contenedores.

Recomendado para el volumen del contrato: 4 núcleos, 8 GB de memoria y disco según el
tamaño de la digitalización (el depósito guarda el original, la matriz PDF/A y la copia de
consulta de cada carpeta).
