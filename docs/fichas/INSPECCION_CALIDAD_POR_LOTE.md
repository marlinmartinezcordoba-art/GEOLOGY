# Inspección de calidad por lote

Decisión D-42. Pruebas: `backend/tests/test_inspeccion.py`. Pantallas: proyecto → pestaña **Calidad por lote**
y la página de cada inspección.

ARCA ya revisa cada archivo al cargarlo (resolución, blancos, duplicados, formato). La inspección por lote es
el control de aceptación que pide una interventoría: se toma una muestra del lote, se revisa a mano y el lote
se acepta o se rechaza según un plan fijado de antemano.

## El plan de muestreo

Lo fija la dirección, con motivo. ARCA trae una propuesta de ejemplo, pero no deja inspeccionar hasta que la
dirección guarde un plan, porque los valores los pone el pliego.

| Elemento | Opciones |
|---|---|
| Qué se inspecciona | Expedientes, o imágenes (páginas) |
| Tamaño de la muestra | Un porcentaje con un mínimo, o una tabla «tamaño del lote → tamaño de la muestra» (por ejemplo, la que fije el pliego) |
| Catálogo de defectos | Cada defecto con su severidad: crítico, mayor, menor o limitación del original |
| Aceptación | Cuántos defectos críticos, mayores y menores se aceptan en la muestra |
| Frente de productividad | Dónde se cuenta la inspección en el tablero |
| Exigir para entregar | Si está marcado, el paquete de entrega solo incluye expedientes de lotes aceptados |

Cada inspección guarda una copia del plan con el que se hizo: cambiar el plan no cambia las inspecciones
anteriores.

## La inspección

1. **Muestra.** Quien inspecciona abre la inspección de un lote de la base de cajas. ARCA cuenta el lote (solo
   lo digitalizado), calcula el tamaño de la muestra y la elige al azar con una **semilla registrada**: la
   misma semilla da la misma muestra, así la interventoría puede comprobarla. Hay una sola inspección abierta
   por lote.
2. **Revisión.** Por cada elemento de la muestra se ve la imagen y se marcan sus defectos del catálogo, con una
   nota si hace falta, o «sin defectos». **Quien cargó los archivos de un expediente no puede inspeccionarlo.**
3. **Decisión.** Al cerrar, con toda la muestra revisada, ARCA cuenta los defectos por severidad. Si alguna
   severidad pasa lo aceptado, el lote se rechaza. Nadie acepta ni rechaza a mano. Las limitaciones del
   original (deterioro, ilegible de origen) se registran, pero no cuentan.
4. **Reinspección.** Un lote rechazado se corrige y se inspecciona de nuevo, con una muestra nueva. La nueva
   inspección queda ligada a la rechazada.

La dirección puede anular una inspección abierta, con motivo. Una cerrada no se anula, porque es evidencia.

## Lo que deja

- **Acta de inspección** en Excel: el plan, la semilla, la muestra con sus defectos, quién revisó cada
  elemento, la decisión y su motivo.
- **Registro de calidad de productividad** (`fCalidad`): cada inspección cerrada agrega su fila (lote,
  tamaño, muestra, defectos por severidad, limitaciones y resultado). Alimenta el tablero y Power BI.
- **Auditoría:** `PLAN_MUESTREO`, `INICIAR_INSPECCION`, `REVISAR_MUESTRA`, `CERRAR_INSPECCION`,
  `ANULAR_INSPECCION` y `EXPEDIR_ACTA_INSPECCION`.
- **Paquete de entrega:** si el plan lo exige, un expediente de un lote sin inspeccionar o rechazado no entra,
  y `pendientes.csv` dice por qué.

## Permisos

| Acción | Quién |
|---|---|
| Fijar el plan, anular | Dirección de proyecto |
| Abrir, revisar y cerrar inspecciones | Quien tiene el permiso de calidad (equipo operativo, dirección) |
| Ver y descargar el acta | Quien lee el inventario del proyecto |

## Lo que falta

- **Tablas normalizadas de muestreo** (por ejemplo, NTC-ISO 2859-1, con niveles de inspección y AQL). Hoy la
  tabla se carga a mano en el plan: si el pliego exige una norma de muestreo, se copia su tabla.
