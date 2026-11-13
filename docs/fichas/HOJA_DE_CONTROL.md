# Hoja de control sobre lo digitalizado, con visor y origen de cada dato

Decisión D-25. Pruebas: `backend/tests/test_hoja_control.py`. Pantallas:
- proyecto → pestaña **Hoja de control** (bandeja);
- **Elaborar / Verificar** → página del expediente, con los trámites a la izquierda y las páginas
  digitalizadas a la derecha.

## Elaborar

1. **Arranque.** La hoja empieza con **un solo trámite que cubre todas las páginas** del expediente
   digitalizado (los PDF por su parte y las imágenes por su número de página, sin contar lo reemplazado ni lo
   rechazado).
2. **Partir en documentos.** Mientras pasa las páginas en el visor, la persona marca **«Aquí empieza otro
   documento»**. Si se equivoca, **une** el trámite con el siguiente. Ninguna página queda sin documento ni
   en dos documentos.
3. **Folios.** Se calculan desde las páginas, con **imágenes por folio**: 1 si cada imagen es un folio, 2
   si se digitalizó recto y verso. La continuidad se verifica con las reglas R10 a R15 del motor de GEOLOGY.
4. **Datos de cada trámite.**
   - **Fecha:** se escribe como venga («3/2/2020», «julio de 1990», «S/F»). Se guarda completa, parcial
     («1990-07») o sin fecha. Nunca se inventa el día.
   - **Tipo documental:** se elige de la lista de la subserie en la TRD. Si la TRD no trae tipos, se usa el
     que corresponde al nombre de la subserie. Si la subserie tiene un solo tipo, ARCA lo propone. Lo que
     esté fuera de la lista queda con aviso.
   - **Detalle, radicado y observaciones.**
5. **Sin digitalizar:** los trámites y los folios se escriben a mano.
6. **Importar hojas de Excel** (lector de GEOLOGY): una hoja por pestaña. ARCA reconoce la carpeta por el
   nombre de la pestaña o por el encabezado y la **confirma contra el inventario**. No inventa fechas ni
   folios. El libro queda guardado con su huella.

## El origen de cada dato

Cada dato muestra **quién o qué lo puso y de dónde lo tomó**:

| Origen | Ejemplo |
|---|---|
| Persona | «elegido por Ana de la lista de la TRD» / «(no está en la lista de la TRD)» |
| Calculado | «de las páginas 3 a 4 del expediente digitalizado, 1 imagen por folio» |
| TRD | «único tipo documental de la subserie en la TRD …» |
| Clasificación | oficina productora, serie y subserie: «clasificación confirmada con la TRD «…» v2 (Resolución …)» |
| FUID | identificador, expediente, caja y carpeta: «FUID «archivo.xlsx», fila 7» |
| Importado | «importado de «hojas.xlsx», pestaña «CP-2», fila 3» |
| Proyecto | entidad: «entidad cliente del proyecto …» |

Las **fechas extremas** y los **folios** se calculan desde los trámites y se comparan con el FUID. Si no
coinciden, se muestra la alerta («el FUID dice 95»). Manda lo contado en la hoja, y la constancia de la
diferencia queda escrita en la hoja expedida.

## Validación

- **Errores** (impiden enviar): continuidad de folios (sin asignar o repetidos), tipo documental vacío,
  páginas sin cubrir o repetidas, hoja sin trámites.
- **Avisos:**
  - tipo documental fuera de la TRD;
  - fechas fuera de las fechas extremas del FUID;
  - folios distintos del FUID o de lo digitalizado;
  - páginas aún no aprobadas en el control de calidad;
  - unidad sin clasificar.

## Verificar

Lo hace **otra persona** (quien la elabora no la verifica), con el documento a la vista:
- cada trámite se marca **conforme** o **con observación**;
- con todos conformes, se **verifica**;
- si hay observaciones, se **devuelve**: quien la elaboró ve cada observación al lado del trámite;
- una hoja verificada solo se corrige **reabriéndola** con motivo.

## Expedir

La hoja verificada sale en la **plantilla de la entidad**. Es el tipo nuevo `hoja_control`, parametrizable
como el FUID y los rótulos, y trae formato base. Marcadores:
- **Encabezado:** entidad, oficina productora, serie, subserie, código, expediente, fechas extremas
  calculadas, caja, carpeta, total de folios y de documentos, la constancia de diferencia de folios, quién
  elaboró y quién verificó.
- **Fila por trámite:** orden, fecha o «S. F.», tipo, detalle, folios desde y hasta, número de folios,
  radicado (o «N/A») y observaciones.

Queda en Entregables con su huella.

## API

`/api/v1/proyectos/{id}/hojas-control`:
- bandeja (`?estado=&q=`) · `POST /importar`
- `GET|POST /unidades/{u}`
- `GET /unidades/{u}/paginas/{n}/imagen` (PNG para el visor) y `/original` (archivo verificado)
- `PUT /unidades/{u}/imagenes-por-folio`
- `POST|PATCH|DELETE /unidades/{u}/tramites[/{t}]`
- `POST …/{t}/dividir`, `…/{t}/unir`, `…/{t}/revisar`
- `POST /unidades/{u}/enviar`, `/verificar`, `/devolver`, `/reabrir`, `/expedir`

Permisos (migración 0009):
- `hoja_control:elaborar` y `hoja_control:verificar`: Administración, Dirección de proyecto y Equipo
  operativo (la segregación es por persona).
- Expedir: `entregables:expedir`.

## Pendiente

- **OCR local (M13):** que ARCA proponga dónde empieza cada documento, la fecha y el tipo documental a
  partir del texto, como propuesta con su confianza, para que la persona confirme.
- Configurar por lote si se hace hoja de control, ISAD(G) o ambas (D-26).
- Llevar los folios contados al FUID de salida.
