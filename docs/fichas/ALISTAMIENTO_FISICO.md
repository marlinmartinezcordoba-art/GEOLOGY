# Alistamiento físico por expediente

Decisión D-44. Pruebas: `backend/tests/test_alistamiento.py`. Pantalla: proyecto → pestaña **Alistamiento físico**.

El alistamiento es el trabajo físico sobre cada expediente antes de digitalizarlo. En un proyecto de
historias laborales es lo que más se paga y lo que más revisa la interventoría. Antes solo se registraba como
cantidades diarias en productividad; ahora queda por expediente.

## Actividades del proyecto

Las fija la dirección, con motivo (`PLAN_ALISTAMIENTO`). Cada una tiene un nombre, si pide cantidad (folios o
unidades) y si es obligatoria. ARCA trae una propuesta de ejemplo que se ajusta al pliego:

| Actividad de ejemplo | Cantidad |
|---|---|
| Depuración (retiro de duplicados y documentos de apoyo) | — |
| Ordenación cronológica | — |
| Foliación | Folios |
| Retiro de material abrasivo (ganchos, clips, grapas) | — |
| Cambio de unidad de conservación (carpeta) | Unidades |
| Rotulación de la carpeta | — |

## Registro

- **Por caja entera o expediente por expediente.** Se elige la actividad y se marcan los expedientes.
- **Con cantidad** cuando la actividad la pide. Para la foliación, ARCA sugiere los folios del FUID para que se
  corrijan con lo contado.
- Queda **quién y cuándo** (`REGISTRAR_ALISTAMIENTO`). Volver a registrar actualiza.
- **Deshacer** exige motivo (`DESHACER_ALISTAMIENTO`).

## Avance y controles

- **Avance por caja y por actividad**, y cuántos expedientes tienen completo el alistamiento obligatorio.
- **Productividad lo cuenta solo:** `alistamiento.<codigo>` cuenta expedientes y `alistamiento.<codigo>.cantidad`
  suma la cantidad (por ejemplo, `alistamiento.foliacion.cantidad` = folios foliados), en la columna
  `Fuente_Automatica` de `dActividades`.
- **Hoja de control:** avisa el alistamiento obligatorio pendiente y si la foliación registrada no coincide con
  los folios de la hoja.
- **Paquete de entrega:** si el plan lo exige, solo entran expedientes con el alistamiento obligatorio
  completo, y `pendientes.csv` dice qué falta. El `metadatos.json` de cada expediente lleva su alistamiento.

## Permisos

| Acción | Quién |
|---|---|
| Fijar las actividades | Dirección de proyecto |
| Registrar y deshacer | Quien carga lo digitalizado (equipo operativo, dirección) |
| Ver el avance | Quien lee el inventario del proyecto |
