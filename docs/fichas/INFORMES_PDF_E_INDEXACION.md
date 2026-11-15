# Informe de avance, PDF con logo e indexación para el SGDEA

Decisión D-47. Pruebas: `backend/tests/test_informes.py`. Pantalla: proyecto → **Entregables**.

## PDF/A con el logo de la entidad

- **Logo:** Entregables → **Logo de la entidad** (PNG o JPEG de hasta 2 MB). Va en el encabezado de los PDF.
- **Entregables en PDF:** cada entregable expedido en Excel (FUID, rótulos, hoja de control, lista de chequeo…)
  se descarga también en PDF, con el logo, en **PDF/A-2b validado**.
- La fuente va incrustada, así que se ve igual en cualquier equipo. Si un PDF no se puede aprobar como PDF/A, sale
  como PDF común y la respuesta lo dice.
- El Excel de la entidad sigue siendo el original del entregable; el PDF es su presentación.

## Informe de avance para la interventoría

Entregables → **Informe de avance**: se elige el periodo y sale en **PDF/A** (con el logo) o **Excel**. Lo arma
ARCA con los datos; el mismo periodo da los mismos números. Secciones:

- el proyecto y el periodo;
- el avance por frente a la fecha de corte;
- la digitalización y el OCR del periodo;
- el alistamiento físico (en el periodo y acumulado) y el diagnóstico de conservación;
- las hojas de control verificadas y las inspecciones por lote cerradas;
- las historias laborales con sus alertas, las entregas digitales y las novedades abiertas;
- la **evidencia**: la verificación de la cadena de auditoría y los eventos del periodo.

Lo pueden sacar quienes ven la productividad, incluida la entidad cliente. Queda en la auditoría
(`EXPEDIR_INFORME_AVANCE`).

## Archivo de indexación para el SGDEA

Cada SGDEA carga los expedientes con su propio archivo: unas columnas con unos nombres. Se configura por
proyecto en Entregables → **Archivo de indexación para el SGDEA**. Queda como el parámetro versionado
`entrega.indexacion`, con motivo. Se define:

- **una fila por** expediente, o por cada documento de la hoja de control;
- el **separador** y el **nombre del archivo**;
- las **columnas**: cada una con el nombre que pide el SGDEA y el dato de ARCA que lleva. Entre los datos: el
  identificador y las fechas del expediente, la TRD, el titular, la ruta y la huella del PDF dentro del paquete y
  los datos de cada documento. También puede llevar un texto fijo.

Lo que no sirve (un dato que no existe, un dato de documento con una fila por expediente) se rechaza al guardar.
El archivo va dentro del paquete de entrega, con su huella en el manifiesto.
