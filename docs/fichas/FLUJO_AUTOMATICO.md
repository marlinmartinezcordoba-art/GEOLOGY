# Flujo automático

Decisión D-39 (resuelve D-04 por ahora). Pruebas: `backend/tests/test_flujo.py`. Pantalla: proyecto →
pestaña **Flujo automático**.

## Qué hace

Al cargar lo digitalizado, ARCA avanza sola cada expediente hasta donde tiene que decidir una persona. Sigue
sola cuando esa persona actúa.

| Etapa | Quién | Qué pasa |
|---|---|---|
| Calidad | Persona, si hay alertas | Con archivos por revisar o en recaptura, el flujo espera la decisión de calidad |
| OCR | ARCA | Lee las páginas pendientes por tandas (30 por vez) hasta terminar |
| Hoja de control (si el lote la lleva) | ARCA, luego dos personas | Crea la hoja y la propone desde el OCR: corte de documentos, tipo de la TRD, fecha, detalle y radicado. Una persona confirma y envía; otra verifica |
| Descripción ISAD(G) (si el lote la lleva) | ARCA, luego dos personas | Con la hoja verificada (o, sin hoja, con el OCR) crea la descripción con lo deducido y el título y alcance propuestos. Una persona confirma y envía; otra aprueba |
| Listo | — | Todo lo que el lote lleva está hecho |

**Qué lo pone en marcha:**
- la carga de archivos;
- la decisión de calidad y la asignación de un archivo;
- enviar, verificar, devolver o reabrir la hoja;
- enviar, aprobar, devolver o reabrir la descripción.

**Poner en cola lo digitalizado** encola lo que se cargó antes de que existiera el flujo.

**El flujo nunca decide por una persona:** solo calcula y propone. Lo que crea no tiene «persona
elaboradora». Elabora quien confirma y envía, así quien verifica o aprueba puede ser cualquiera distinta de
esa persona. Actúa a nombre de quien originó el trabajo y queda en la auditoría como `FLUJO_AUTOMATICO`, con
lo que hizo y qué lo originó.

## La cola

- **Tabla `trabajos`.** No requiere instalar nada adicional.
  - Un trabajo se toma con una actualización condicionada, así dos trabajadores no toman el mismo.
  - No se duplica: una sola tarea pendiente por expediente.
  - Si falla por algo inesperado, se reintenta hasta 3 veces. Si es un error de regla, queda como error con
    su mensaje y se puede reintentar desde el tablero.
- **Trabajador:**
  - **en local**, un hilo de la aplicación revisa la cola cada 3 segundos (`ARCA_TRABAJOS_EN_PROCESO`,
    encendido por defecto en local);
  - **en producción**, uno o varios procesos aparte: `python -m arca.modulos.flujo.trabajador`.
- **Procesar ahora** atiende una tanda en el momento: sirve si no hay trabajador.
- Cuando el volumen lo pida, la cola puede pasar a Celery con Redis sin cambiar el flujo.

## Tablero

- Cuántos expedientes hay en cada etapa, con las que esperan a una persona resaltadas.
- La cola: en cola, en curso, hechos y con error, y qué trabajador está activo.
- La lista por etapa: qué falta, qué hizo ARCA y un enlace para **Atender** (a la hoja o a la descripción).
- Los trabajos con error, para reintentarlos.

Se actualiza solo cada 6 segundos.

## API

`/api/v1/proyectos/{id}/flujo`:
- `GET` (tablero) · `GET /unidades?etapa=` · `GET /errores`
- `POST /iniciar` · `POST /procesar` · `POST /errores/{t}/reintentar`

Permisos: consultar, `inventario:leer`; operar, `captura:cargar`. Migración 0013.
