# M13 · OCR local y propuesta de la hoja de control

Decisión D-21 (OCR local) y D-35. Pruebas: `backend/tests/test_m13_ocr.py`. Las pruebas que necesitan el
motor se omiten solas si el servidor no lo tiene; las reglas del analizador se prueban siempre.

## Motor

- **Tesseract** (5.x) instalado en el servidor, con el idioma español. Los documentos **no salen del
  servidor**: no se usa ningún servicio externo.
- Instalación: `apt-get install tesseract-ocr tesseract-ocr-spa`.
- `GET /estado` dice si el OCR está disponible y con qué idiomas.
- Cada página se lee **una sola vez** desde el original verificado contra su huella, al tamaño original.
- Se guarda el texto por renglón con la confianza de cada uno, el motor y su versión, el idioma y la
  duración. Se guarda por archivo y página del archivo, para que una recaptura o un cambio de orden no
  confunda a qué imagen pertenece el texto.
- **Por tandas:** hasta que exista la cola de procesos en segundo plano (D-04), la pantalla pide tandas
  de 10 páginas hasta terminar y se puede detener. Volver a pedir continúa donde quedó.

## Pantallas

- **Bandeja de la hoja de control → OCR local:**
  - avance del proyecto: leídas, pendientes, confianza media, páginas con confianza baja, sin texto y con
    error;
  - **Leer páginas pendientes**;
  - **Buscar en el contenido** de los documentos, con el fragmento y el enlace al expediente.
- **Hoja de control:**
  - **Leer con OCR y proponer**;
  - en el visor, **Texto OCR** muestra lo leído en la página, renglón por renglón, y marca los renglones
    con confianza baja.

## Qué propone y cómo

Nada de lo que propone el OCR queda como dato: queda como **propuesta**, con la página, el renglón y la
confianza de donde se tomó.

| Dato | Regla |
|---|---|
| Dónde empieza cada documento | La página empieza un documento nuevo si su encabezado trae el título de un tipo documental y no dice «continuación», «anexo» ni «página N de», y además cambia el tipo o el número |
| Tipo documental | Primero la lista de la subserie en la TRD; si no, una lista general de tipos frecuentes (y queda el aviso de que no está en la TRD) |
| Fecha | La primera fecha del encabezado, normalizada con las reglas del motor (día primero; la fecha parcial queda parcial) |
| Detalle | El renglón del título y el siguiente, como están escritos. Solo se corrige la confusión conocida «N.2» → «N.º» |
| Radicado | Si aparece escrito como «Radicado No. …» |

**Confianza del corte:**
- **alta:** el tipo es de la TRD y el OCR leyó el renglón con 80 % o más;
- **media:** el OCR leyó el renglón con 60 % o más;
- **baja:** en otro caso.

## Confirmar

- Lo propuesto aparece con la marca **«OCR · por confirmar»** y **bloquea el envío** de la hoja a
  verificación.
- La persona corrige lo que haga falta (el dato pasa a ser suyo) y pulsa **Confirmar lo propuesto** para
  aceptar el resto. El origen queda como «confirmado por … (propuesto por OCR de la página 3: «…»,
  confianza 91 %)».
- Si la hoja ya tenía trámites trabajados, la propuesta del OCR solo los reemplaza si la persona lo
  confirma.

## API

`/api/v1/proyectos/{id}/ocr`:
- `GET /resumen`
- `POST /leer?limite=` (tanda del proyecto; permiso `captura:cargar`)
- `GET /unidades/{u}` (texto por página)
- `POST /unidades/{u}/leer` (permiso `hoja_control:elaborar`)
- `GET /buscar?q=`

En la hoja de control:
- `POST /hojas-control/unidades/{u}/proponer-ocr` (`{reemplazar}`)
- `POST /hojas-control/unidades/{u}/tramites/{t}/confirmar`

Migración 0010: tabla `textos_pagina`.

## Pendiente

- Cola de procesos en segundo plano (D-04) para leer lotes grandes sin la pantalla abierta.
- PDF/A con capa de texto (OCRmyPDF) como copia de preservación del expediente.
- Medir la calidad del OCR con un corpus anonimizado y autorizado (pregunta abierta 7).
- HTR (escritura a mano) y propuestas con IA sobre el texto (M14 a M16).
