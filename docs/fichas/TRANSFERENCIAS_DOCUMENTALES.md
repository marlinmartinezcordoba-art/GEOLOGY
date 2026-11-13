# Transferencias documentales y ciclo vital (gestión → central → histórico)

Decisión D-32 (desarrolla D-24). Pruebas: `backend/tests/test_transferencias.py`. Pantalla: proyecto →
pestaña **Transferencias**.

## Ciclo vital

Cada unidad documental tiene una **fase**: archivo de gestión, archivo central o archivo histórico. Nace en
gestión y cambia solo de dos maneras, y las dos quedan en el historial (`movimientos_fase`):

1. **Por una transferencia recibida.**
2. **Por la fase de partida.** Sirve para un fondo acumulado que ya está en el archivo central o histórico.
   Se registra por cajas, una sola vez por unidad y con motivo.

La descripción ISAD(G) no depende de la fase (D-24).

## Plan a la fecha de corte

Muestra cuántas unidades hay en cada fase y cuántas se pueden transferir, por dependencia:

| | Primaria (gestión → central) | Secundaria (central → histórico) |
|---|---|---|
| Cumple | Fecha final + AG ≤ corte | Fecha final + AG + AC ≤ corte |
| Disposición | Cualquiera | Solo CT, S o D. Lo que tiene E va a la disposición final, no al histórico |
| Requisito | Clasificada y confirmada, en gestión, libre | Clasificada y confirmada, en central, libre |

- **Aún no cumple:** puede incluirse como **anticipada**, con aviso.
- **Sin fecha final o sin tiempos:** no se sabe si cumplió, y se dice.
- **Selección (S):** va al histórico con el aviso de transferir solo lo elegido por muestreo.

## Flujo

1. **Preparar.** Crea el borrador con todo lo que cumple, de una dependencia o de todas. Se pueden agregar
   unidades (las anticipadas quedan marcadas) y quitarlas.
2. **Enviar.** Exige que cada unidad tenga folios. Una unidad no va en dos transferencias abiertas.
3. **Recibir.** Lo hace **otra persona** con el permiso `transferencias:recibir`, unidad por unidad:
   - lo recibido cambia de fase;
   - lo devuelto se queda donde estaba, con su observación, y queda libre para otra transferencia.
4. **Devolver completa.** El archivo receptor la regresa con motivo. Se corrige y se reenvía.
5. **Anular.** Solo en borrador o devuelta, con motivo.

## Inventario de la transferencia

**Inventario FUID** expide el FUID con la plantilla vigente de la entidad. Llena:
- en el encabezado: `{{objeto}}` (transferencia primaria o secundaria), `{{numero_transferencia}}`,
  `{{oficina_productora}}`, `{{codigo_oficina}}` y `{{fecha_corte}}`;
- en cada fila: `{{fila.codigo_clasificacion}}`, `{{fila.serie}}`, `{{fila.subserie}}`,
  `{{fila.dependencia}}` y `{{fila.fase}}`.

Queda en Entregables con su huella y con el número de la transferencia en el filtro. Los mismos campos de
clasificación sirven en el FUID general y en el rótulo de carpeta.

## API

`/api/v1/proyectos/{id}/transferencias`:
- `GET /plan?fecha_corte=`
- `GET` lista · `POST` crear
- `GET /{t}` · `GET /{t}/candidatas`
- `POST /{t}/agregar`, `/quitar`, `/enviar`, `/recibir`, `/devolver`, `/anular`, `/inventario`
- `POST /fase-de-partida` (unidades o cajas)
- `GET /unidades/{u}/historial`

Permisos (migración 0007):
- `transferencias:gestionar`: Administración, Dirección de proyecto y Equipo operativo.
- `transferencias:recibir`: Administración y Dirección de proyecto.
- Para consultar basta `inventario:leer`.

## Pendiente

- Acta de transferencia firmada y cronograma anual de transferencias.
- Disposición final: eliminación con acta y publicación, selección por muestreo y digitalización (lo que
  queda en central con «Retención cumplida»).
