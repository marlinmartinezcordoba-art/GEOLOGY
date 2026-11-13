# Disposición final: eliminación, selección y digitalización

Decisión D-33. Pruebas: `backend/tests/test_disposicion.py`. Pantalla: proyecto → pestaña **Disposición final**.

## Principio

Eliminar es irreversible. ARCA prepara el inventario y documenta cada paso, pero **no decide**. Es el mismo
principio del motor de disposición de GEOLOGY: proponer y explicar, nunca marcar ni excluir por su cuenta.

Ninguna unidad se elimina sin:
1. inventario;
2. aprobación del comité, registrada por una persona distinta de quien preparó el proceso;
3. publicación del inventario por el plazo que fije la entidad;
4. acta de eliminación.

Lo eliminado **no se borra de ARCA**: queda en fase «eliminada», con su inventario, su historial y el acta.

## Qué entra

Entra lo clasificado y confirmado que cumplió **toda** su retención (gestión + central) a la fecha de corte,
siempre que:
- esté en el archivo de gestión o en el central;
- no tenga una disposición ya aplicada;
- no vaya en otra transferencia ni en otro proceso.

La TRD o TVD decide el proceso: **E** → eliminación, **S** → selección y **M/D** → digitalización. Lo que
tiene **CT** (conservación total) va por la transferencia secundaria al archivo histórico.

El plan muestra, por tipo y por serie, cuántas unidades cumplen, cuántas aún no y cuántas no tienen
calendario, con el procedimiento que dice la tabla.

## Procesos

| Paso | Eliminación | Selección | Digitalización |
|---|---|---|---|
| 1. Inventario | Borrador con lo que cumple (todas las series o una) | Igual | Igual |
| — | — | **Muestreo**: porcentaje y semilla (la misma semilla da la misma muestra), más ajuste a mano por criterio cualitativo | ARCA verifica que cada unidad tenga la digitalización aprobada |
| 2. Comité | Acta y fecha, registradas por otra persona | Igual; exige la muestra completa | Igual; exige todo digitalizado |
| 3. Publicación | Inicio, plazo en días y enlace. Mientras corre, se retiran unidades por observaciones, con motivo | — | — |
| 4. Ejecución | Al terminar el plazo, con número de acta y método. Las unidades quedan **eliminadas** | Las seleccionadas quedan para la transferencia secundaria; las demás pasan a una **eliminación nueva** en borrador | Se decide el físico: se conserva o pasa a una **eliminación nueva** |

La transferencia secundaria ya no lleva una unidad de selección (S) hasta que esté en la muestra. Tampoco
lleva lo que va en un proceso de disposición abierto.

## Documentos

Se expiden sobre las plantillas vigentes de la entidad, con su huella, y quedan en Entregables.

- **Inventario FUID** del proceso, con el objeto «Eliminación documental», «Selección documental» o
  «Digitalización».
- **Acta de eliminación**: tipo de plantilla nuevo, `acta_eliminacion`, con formato base. Marcadores:
  - `{{numero_acta}}`, `{{acta_comite}}`, `{{fecha_comite}}`;
  - `{{publicacion_inicio}}`, `{{publicacion_fin}}`, `{{publicacion_enlace}}`;
  - `{{metodo}}`, `{{fecha_ejecucion}}`, `{{series}}`, `{{dependencias}}`;
  - las fechas extremas y los totales;
  - una fila por unidad eliminada.

  Solo se expide desde el proceso ejecutado, no desde Entregables.

## API

`/api/v1/proyectos/{id}/disposicion`:
- `GET /plan?fecha_corte=`
- `GET` lista · `POST` crear
- `GET /{p}`
- `POST /{p}/retirar`, `/muestrear`, `/marcar`, `/aprobar`, `/publicar`, `/ejecutar`, `/anular`
- `POST /{p}/documentos/inventario` y `/documentos/acta`

Permisos (migración 0008):
- `disposicion:gestionar`: Administración, Dirección de proyecto y Equipo operativo.
- `disposicion:aprobar`: Administración y Dirección de proyecto.

## Por confirmar con la entidad (no se inventa)

- **El plazo de publicación del inventario de eliminación y si son días hábiles o calendario.** ARCA lo
  pide en cada proceso (por defecto 60) y no lo fija en el código. Verifíquelo con la norma vigente
  (Acuerdo 004 de 2019 del AGN y Decreto 1080 de 2015).
- Quién firma el acta, y si la entidad exige publicar también el acta ejecutada.
