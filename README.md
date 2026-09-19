# KUSTOS

Sistema de Gestión de Documentos Electrónicos de Archivo (SGDEA).

KUSTOS es el sistema completo. **Integra a GEOLOGY y sus funciones**, que hoy resuelven la
intervención archivística del fondo acumulado del Servicio Geológico Colombiano —contrato 733
de 2026—, y las lleva al alcance de un SGDEA: no solo la organización y descripción de un
fondo acumulado, sino la gestión del documento electrónico a lo largo de todo su ciclo de vida.

## Qué hay en este repositorio

```
app/          KUSTOS · el SGDEA
                routers/    API: usuarios, expedientes, archivos, reubicación, instrumentos
                services/   reglas archivísticas: clasificación, descripción ISAD(G), códigos,
                            foliación, fechas, valoración y disposición, formatos oficiales,
                            control de calidad, producción y ritmo
                models/     tablas: expediente, archivo, caja, TVD, trazabilidad, usuario
                tasks/      trabajos en segundo plano
                web/        interfaz

datos/        Inventario de origen, tablas de valoración y plantillas oficiales del
              Servicio Geológico (F-GDM-003 v9, F-GDM-006, F-GDM-007 v4, F-GDM-008 v5).

GEOLOGY/      Plataforma de organización y descripción documental, v2.0.0, completa y
              funcionando. Es la pieza que KUSTOS integra.
                geology/nucleo/     ajustes, base de datos, cola de trabajos, pases de sesión
                geology/modelos/    tablas del dominio
                geology/dominio/    reglas: estados, verificación de hojas, descripción ISAD(G),
                                    formatos oficiales, división de documentos, cajas, lectores
                geology/rutas/      API: /cargue /unidades /ubicacion /instrumentos /cuentas /consulta
                geology/interfaz/   interfaz web
                docker-compose.yml  cuatro servicios: FastAPI, Celery, PostgreSQL 15, Redis 7
                docs/               DESPLIEGUE.md y MANUAL.md
                scripts/            carga de datos, cuentas, migración, mantenimiento
```

## Dónde está corriendo

Hoy, en equipo local con Docker Compose y en entorno de desarrollo. Está en trámite el
servidor con Hometic para publicarlo con dominio propio y TLS.

La arquitectura, el dimensionado del fondo y lo que hay que provisionar están documentados
en `GEOLOGY/docs/DESPLIEGUE.md`.

## Arranque de GEOLOGY

```bash
cd GEOLOGY
cp .env.example .env          # escriba la clave de PostgreSQL, GEOLOGY_CLAVE y las llaves de los lectores
docker compose up -d --build
```

Una sola vez, después:

```bash
docker compose exec servidor python scripts/cargar_inventario.py
docker compose exec servidor python scripts/cargar_contexto.py
cp datos/equipo.ejemplo.csv datos/equipo.csv     # escriba el equipo
docker compose exec servidor python scripts/crear_usuarios.py
docker compose exec procesador python scripts/revisar_motor.py
```

La interfaz queda en `http://localhost:8080/app` y el estado del sistema en
`http://localhost:8080/estado`.

## El fondo que se interviene

Del inventario de origen del contrato:

| | |
|---|---|
| Carpetas | 7.699 |
| Cajas de origen | 1.020 |
| Folios | 1.213.710 |
| Metros lineales | 121,4 |
| Promedio por carpeta | 157,6 folios |
| Carpeta más extensa | 15.289 folios |

---

Contrato 733 de 2026 · Servicio Geológico Colombiano · Hometic SAS
