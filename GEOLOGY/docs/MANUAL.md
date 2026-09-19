# GEOLOGY · Manual de uso

## Perfiles

| Perfil          | Qué ve                                                                 | Qué hace |
|-----------------|------------------------------------------------------------------------|----------|
| administradora  | Todas las pestañas, incluidas Consulta y Cuentas                       | Aprueba descripciones, retira expedientes, administra cuentas y habilitaciones |
| lider           | Inicio, Cargue, Hojas de control, Proceso, Revisión, Localización, Reubicación, Instrumentos, Calidad, Centro de control | Aprueba descripciones |
| equipo          | Las mismas, según su función (Hoja de control, Descripción o Ambas)    | Carga, diligencia y revisa hojas; genera y valida descripciones |
| consulta        | Localización, Instrumentos, Calidad, Centro de control                 | Auditoría interna; no interviene expedientes |
| entidad         | Únicamente Consulta                                                     | Servicio Geológico: descarga hojas de control, ISAD(G) y FUID; ve imágenes si se le habilita |

## Flujo de un expediente

1. **Cargue.** Se suelta el documento digitalizado. El nombre del archivo lleva el código de
   carpeta (`AC-CP-00374.pdf`, `CARPETA_00374.pdf`, `carpeta-00374- 2.pdf`). Solo entran
   carpetas del inventario de origen del contrato. La recepción técnica mide páginas,
   resolución y capa de texto y lo deja anotado.
2. **Lectura.** En segundo plano, la plataforma lee el documento y propone la hoja de control:
   trámites, fechas, tipos documentales, foliación. Queda en *Hoja de control en elaboración*.
   Si no hay lector disponible, la hoja se diligencia a mano en la pestaña Hojas de control o
   se importa desde Excel.
3. **Verificación.** Al guardar la hoja, la plataforma corrige lo corregible (rangos de folios,
   numeración) y contrasta con el inventario. Queda *Hoja de control por revisar*.
4. **Revisión humana.** Alguien del equipo revisa la hoja y la marca revisada. Desde este
   momento la carpeta se publica al perfil de la entidad.
5. **Descripción ISAD(G).** Quien tiene la función de descripción la genera; la plataforma
   resuelve fechas extremas, periodo y subserie de la tabla de valoración. Queda *Descripción
   por validar*; una persona la valida y la dirección la aprueba (*Archivado*).
6. **Reubicación.** Se asigna caja definitiva (AH-CJ) y número de carpeta en la caja. Queda
   *En inventario de salida*.
7. **Instrumentos.** FUID F-GDM-003 v9, hojas de control F-GDM-007 v4, rótulos F-GDM-006 y
   F-GDM-008 v5, base ISAD(G) en la plantilla del proyecto. Todo sale sobre las plantillas
   oficiales; la plataforma las llena.

## Expedientes por partes y documentos de gran volumen

Un libro empastado llega de dos maneras y las dos terminan igual.

**Por partes nombradas por quien digitalizó.** `carpeta-00001- 1.pdf`, `carpeta-00001- 2.pdf`,
`AC-CP-00001_3.pdf`, `CARPETA 00001 parte 4.pdf`: la plataforma reconoce el código de carpeta
y el número de parte en cualquiera de esas formas. Las partes se pueden subir en cualquier
orden; la lectura las toma en el orden de su número, con la numeración de trámites y de
folios corrida de una a la siguiente, y sale UNA hoja de control. Si falta una parte en la
mitad (1, 2, 4), queda anotado en la bitácora y en la hoja; al cargar la que falta se vuelve a
levantar. Si una parte llega mientras se está leyendo, la plataforma vuelve a leer el
expediente completo en orden.

**Entero, en un solo archivo.** Un documento de más de `PAGINAS_POR_PARTE` páginas (250 por
defecto; un libro de 1.000 imágenes da cuatro partes) lo divide la plataforma en partes
consecutivas dentro del depósito, cada una con el rango de páginas del original que abarca
(1–250, 251–500, …). Las páginas se copian tal cual, sin tocar la imagen; la huella del
archivo entero queda registrada en cada parte y en la bitácora, de modo que la secuencia se
puede demostrar y un segundo cargue del mismo archivo se reconoce como duplicado.

Un expediente no se mezcla: si ya está por partes no entra un archivo entero, y si ya está
entero no entra una parte suelta. Para cambiar de modalidad se retira el expediente y se
vuelve a cargar.

En el visor, las partes aparecen como botones (parte 1, parte 2, …) con su rango de páginas.

## Consulta de la entidad

La dirección crea la cuenta en la pestaña Cuentas con rol *Entidad (consulta SGC)* y marca
qué puede ver: hojas de control, base ISAD(G), inventario FUID e imágenes digitalizadas
(las imágenes vienen apagadas). La cuenta entra a una sola pestaña, Consulta, donde busca
por carpeta, nombre o código de referencia, filtra por caja y periodo y descarga los
instrumentos en los formatos oficiales. Solo ve unidades cuya hoja de control ya fue
revisada; la base ISAD(G) solo lleva descripciones validadas y el FUID solo lo que está en
caja definitiva. Ninguna información del proceso interno (cola, lecturas, reparto de trabajo,
centro de control) le es visible ni accesible por la API.
