# Historias laborales

Decisión D-43. Pruebas: `backend/tests/test_historias.py`. Pantalla: proyecto → pestaña **Historias laborales**.

El proyecto es de digitalización masiva y organización de historias laborales. Una historia laboral es el
expediente de una persona vinculada a la entidad (Acuerdo AGN 001 de 2024, título 9, capítulo 5).

## Lo que dice la norma (Acuerdo 001 de 2024, artículos 9.5.1 a 9.5.5)

- Se conforma con los **tipos documentales mínimos** de la serie descritos en el Banco Terminológico (BANTER)
  del AGN. La entidad puede agregar otros.
- El área de custodia es de **acceso restringido**, con control estricto de la consulta.
- Se **cierra** cuando termina el trámite de retiro y el pago de las prestaciones sociales definitivas.
  Después de transferida al archivo central no se le agregan documentos.
- **Retención recomendada:** 2 años en el archivo de gestión, contados desde la desvinculación, y mínimo 80
  años en el archivo central. La entidad puede aumentarla, no reducirla.

## Configuración del proyecto (dirección)

- Si el proyecto es de historias laborales.
- Qué códigos de la TRD son historias laborales (vacío = todo el proyecto).
- Los **tipos documentales mínimos**: los marca la dirección según el BANTER y la TRD de la entidad. ARCA
  muestra como ayuda los tipos de la TRD del proyecto. No trae una lista propia: no inventa la norma.

## Lo que automatiza ARCA

| Qué | Cómo | Dónde se ve |
|---|---|---|
| Titular | Del nombre de la unidad en el FUID («Historia laboral PÉREZ GÓMEZ ANA · C.C. 52.123.456»): número, tipo y nombre. Si el FUID no trae el número, el que más se repite en el OCR junto a «C.C.», «cédula», «identificado con»… Cada dato dice de dónde salió; lo confirmado no se vuelve a proponer | Pestaña, flujo automático (al terminar el OCR) |
| Documentos de otra persona | Páginas donde aparece un número de documento distinto al del titular | Pestaña y avisos de la hoja de control |
| El número del titular no aparece | Ningún documento leído trae el número del titular | Pestaña y avisos de la hoja |
| Tipos mínimos que faltan | Los obligatorios que no están en la hoja de control | Pestaña y avisos de la hoja |
| Orden cronológico | Un documento con fecha anterior al que lo precede (para todo expediente, no solo historias laborales) | Avisos de la hoja |
| Titular repetido | Dos expedientes con la misma persona (tomos o duplicados) | Pestaña y avisos de la hoja |
| Consulta | Se busca por número de documento y por nombre | Consulta |
| Paquete de entrega | El `metadatos.json` lleva el titular | Paquete de entrega |

Un número de documento solo se reconoce junto a su rótulo («C.C.», «cédula de ciudadanía», «T.I.», «C.E.»,
«identificado con»…): un radicado, un NIT o un folio no se confunden con un documento de identidad.

## FUID, rótulos y hoja de control con el titular

El FUID de salida, los rótulos de carpeta y la hoja de control tienen las marcas del titular:
`{{fila.tipo_documento}}`, `{{fila.numero_documento}}`, `{{fila.titular}}`, `{{fila.cargo_titular}}`,
`{{fila.fecha_vinculacion}}` y `{{fila.fecha_retiro}}` (en la hoja de control, sin `fila.`).

## Lista de chequeo

Por cada historia con hoja de control, en la plantilla vigente de la entidad (tipo «Lista de chequeo de la
historia laboral»; ARCA trae un formato de partida). Una fila por cada tipo documental mínimo (si está, sus
folios y su fecha; si no, «No está en el expediente») y después los demás tipos de la hoja («No es de los tipos
mínimos de la serie»). El encabezado lleva el titular, los totales, cuáles faltan y las alertas de la historia.
Se expide desde la pestaña **Historias laborales** y queda guardada con su huella como cualquier entregable.

## Acceso restringido

La configuración trae **acceso restringido** activado (artículo 9.5.3): aunque la TRD no lo marque, en la
consulta quien no tiene el permiso de consulta reservada solo ve los metadatos de una historia laboral (no el
texto, ni las imágenes, ni los fragmentos), y la consulta lo muestra como «restringida (historia laboral)». La
dirección puede desactivarlo si la TRD de la entidad ya define el acceso.

## La persona confirma

Quien elabora la hoja de control confirma el titular y completa el cargo, la dependencia y las fechas de
vinculación y retiro. Lo que escribe queda con su nombre como origen, y queda en la auditoría
(`PROPONER_TITULAR`, `CONFIRMAR_TITULAR`, `CONFIGURAR_HISTORIAS`).

## Lo que falta

- **Retención desde el retiro:** el calendario de transferencias de una historia laboral debe contarse desde
  la fecha de retiro confirmada, no desde la fecha final del FUID.
