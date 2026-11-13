"""
Levantamiento de la hoja de control a partir del documento digitalizado.

El modelo recibe el documento completo, no un texto extraído, porque además de leer lo que
dice tiene que ver el estado del papel: manchas de humedad, rasgaduras, dobleces, tinta
desvanecida, faltantes. Eso es lo que alimenta la columna de observaciones de la hoja de control y
las características físicas del elemento 3.4.4 de la descripción.

Lo que el modelo hace, y lo que NO hace:

  Hace     leer el documento, separar los trámites, reconocer fechas y tipos documentales,
           proponer la foliación, anotar el estado de conservación de lo que ve y —en una
           segunda pasada, ya con el periodo resuelto— proponer a qué subserie de la tabla
           de valoración pertenece lo que leyó.
  No hace  decidir el periodo, que sale de las fechas extremas; ni la valoración; ni el
           código de referencia; ni escoger una subserie que no esté en la tabla del
           periodo: la lista que se le entrega es cerrada y no puede salirse de ella.

Todo lo que produce entra como PROPUESTA. Una persona la revisa antes de que exista
descripción, tal como quedó definido el flujo.
"""
from __future__ import annotations

CAMPOS_TRAMITE = ("no_item", "fecha", "tipo_documental", "folio_desde", "folio_hasta",
                  "observaciones")


def instruccion_hoja_de_control(contexto: dict, texto_reconocido: str = "") -> str:
    """Instrucción para el levantamiento de la hoja de control del expediente."""
    apoyo = ""
    if texto_reconocido:
        apoyo = f"""

APOYO. Abajo va el texto que un motor de reconocimiento óptico sacó de este mismo expediente.
Úselo para no tener que descifrar lo mecanografiado y para copiar cifras y nombres sin
equivocarse. NO lo tome como verdad: sobre manuscrito antiguo ese motor devuelve disparates,
se salta renglones y confunde caracteres. Cuando el texto y la imagen no concuerden, mande lo
que usted vea en la imagen. Si una parte del texto no tiene sentido, ignórela.

--- texto reconocido, puede venir con errores ---
{texto_reconocido}
--- fin del texto reconocido ---
"""
    return f"""Usted es archivista y está levantando la hoja de control de un
expediente de {contexto.get('fondo') or 'el fondo documental del proyecto'}.

Le adjunto el expediente digitalizado completo. Léalo de principio a fin y sepárelo en
trámites.{apoyo} Un trámite es cada unidad documental con sentido propio dentro del expediente:
un oficio con sus anexos, un informe, un acta, un memorando, una resolución, un contrato.
Si un oficio trae anexos que le pertenecen, van dentro del mismo trámite, no aparte.

Lo que dice el inventario de origen. ATENCIÓN: este inventario se levantó hace años, con la
información que había entonces, y NO es fiable. Es una referencia para contrastar, no un dato
que usted deba respetar. Si el documento dice otra cosa, mande el documento y dígalo.
  Código de carpeta: {contexto.get('codigo_carpeta')}
  Periodo institucional: {contexto.get('periodo') or 'no asignado'}
  Rango del periodo: {contexto.get('rango_periodo') or 'no disponible'}
  Asunto según el inventario de origen: {contexto.get('asunto') or 'no disponible'}
  Folios que declara el inventario: {contexto.get('folios') or 'no disponible'}
  Fechas que declara el inventario: {contexto.get('fechas_inventario') or 'no disponible'}

Para cada trámite entregue:

  no_item          número consecutivo empezando en 1, en el orden en que aparece.
  fecha            la del trámite, en formato año-mes-día. Si el documento trae varias
                   fechas, tome la MÁS RECIENTE del propio trámite, que es la que cierra la
                   actuación. Si solo se lee el mes y el año, escriba año-mes. Si solo el
                   año, escriba el año. Si no hay ninguna fecha legible, escriba SF.
                   No deduzca fechas por el contexto ni las invente.
  tipo_documental  QUÉ ES Y DE QUÉ TRATA ese trámite, en una sola línea, escrito de modo
                   que quien lea la hoja de control sepa qué hay en esos folios sin abrir el
                   expediente. Esta es la casilla más importante de la hoja: es archivo
                   histórico y esta hoja es el instrumento con el que alguien va a buscar
                   dentro de treinta años.

                   Actúe como el archivista experto que analiza el folio y da fe de su
                   contenido. Lea el trámite, entienda de qué se trata y descríbalo. NO copie
                   el asunto del inventario. NO escriba solo la clase de papel.

                   La forma es: tipo documental + de qué trata + los números, nombres propios
                   y lugares que aparezcan escritos en el documento.

                   Así se escribe:
                     INFORMES DE VISITA TÉCNICA N° 2356, 3467 Y 2358 AL PREDIO LA ESPERANZA
                     DE LA VEREDA EL RETIRO
                     Oficio de remisión del informe de interventoría del contrato 045, dirigido
                     al jefe de la Oficina de Planeación
                     Acta de la reunión número 011 del Comité Directivo sobre el plan de acción
                     de la vigencia

                   Así NO se escribe:
                     Oficio
                     Informe
                     Correspondencia
                     Documento del expediente

                   Lenguaje claro y directo, sin adornos. Entre ocho y veinticinco palabras:
                   ni una palabra suelta ni un párrafo. Si un dato no se lee, omítalo; no
                   suponga números ni nombres que no estén escritos.
                   Si el trámite trae anexos, termine con: con anexos.
  no_radicado      el número de radicado si el documento lo trae escrito. Si no lo trae,
                   escriba exactamente N/A en mayúsculas.
  folio_desde      número del primer folio del trámite.
  folio_hasta      número del último folio del trámite.
                   Si el expediente trae foliación escrita, respétela tal cual, aunque
                   tenga saltos o repeticiones. Si no trae foliación escrita, numere las
                   páginas de forma corrida desde el 1. En ninguno de los dos casos escriba
                   nada de esto en observaciones: la foliación se ve en estas dos casillas.
  observaciones    SOLO las novedades, alteraciones y faltantes de la carpeta. Lo que está
                   roto, manchado, incompleto o ilegible. Nada más.

                   Si el trámite no tiene ninguna novedad, esta casilla va VACÍA. No se
                   escribe que está bien, ni que está completo, ni que la foliación es
                   correcta: la casilla vacía ya dice eso.

                   Tampoco se escribe aquí ninguna comparación con el inventario de origen
                   ni con el formato único de inventario documental. Si lo que dice el
                   inventario no cuadra con el documento, eso va en las casillas de contraste
                   que tienen su propio sitio, no en esta columna.

                   Frases cortas. Por ejemplo: manchas de humedad en el margen inferior;
                   rasgadura en el borde derecho sin pérdida de texto; tinta desvanecida,
                   lectura parcial; papel quebradizo por acidez; documento con perforación
                   de archivador que afecta el texto; hongos en la esquina superior;
                   dobleces marcados; falta el folio 12; anexo incompleto; copia y no
                   original; sello ilegible; documento en mal estado que requiere
                   intervención de conservación.
                   No invente deterioros que no vea.

                   EN OBSERVACIONES NO SE ESCRIBE la contabilidad de la foliación. Nada de
                   «foliación original», «sin foliar», «se folió de forma corrida», «12
                   folios», «consta de 5 folios», «foliado a lápiz en el extremo superior».
                   Cuántos folios tiene el trámite ya está en folio_desde y folio_hasta, y
                   repetirlo ahí no le sirve a nadie y estorba la lectura de la hoja.

                   Sí van, porque son estado del expediente y no contabilidad: falta el
                   folio 12; el folio 7 está repetido; hay un salto entre el folio 20 y el
                   24; el folio 3 está roto sin pérdida de texto.

Además entregue, para el conjunto del expediente:

  nombre_del_expediente     el campo 7 de la hoja de control. Va CORTO Y GENERAL: de dos a
                            seis palabras que digan QUÉ CLASE de documentación es el
                            expediente, no de qué trata cada folio.

                            Aquí NO van números de informe, ni nombres de personas, ni
                            nombres de predios o lugares, ni fechas, ni radicados. Todo
                            ese detalle ya va en el tipo documental de cada trámite, que es
                            donde corresponde. Este campo es el rótulo del expediente.

                            Así se escribe:
                              Informes de visitas técnicas
                              Informes de interventoría
                              Contratos de prestación de servicios
                              Correspondencia recibida
                              Actas del comité directivo

                            Así NO se escribe:
                              Informes de visita técnica N° 2356, 3467 y 2358 al predio La
                              Esperanza de la vereda El Retiro
                              Expediente
                              Varios

                            Es decir: si el expediente son varios informes de visita técnica,
                            aquí va «Informes de visitas técnicas» y los números de cada informe
                            van en el tipo documental de cada trámite.
  asunto_del_documento      de qué trata REALMENTE el expediente, en una o dos líneas, según
                            lo que usted leyó. Este sí lleva el detalle. No copie el asunto
                            del inventario: escriba el del documento. No es el campo 7: el
                            campo 7 es el de arriba, que va corto.
  coincide_con_el_inventario
                            una de estas tres palabras exactas: «si» cuando el documento trata
                            de lo que el inventario dice; «parcial» cuando trata de eso pero
                            además de otras cosas, o el inventario se queda corto; «no» cuando
                            el documento trata de algo distinto.
  por_que_no_coincide       si puso «parcial» o «no», explique en una línea la diferencia
                            concreta: qué dice el inventario y qué dice en realidad el
                            documento. Si puso «si», deje esto vacío.
  fechas_del_documento      las fechas extrema inicial y final que USTED leyó en el documento,
                            en formato año-mes-día, separadas por «a». Si el inventario declara
                            otras, no lo tenga en cuenta: escriba las del papel.
  folios_contados           cuántos folios contó usted en el expediente. Si el inventario
                            declara otro número, escriba el suyo igual.
  total_folios              el número del último folio.
  estado_general            una o dos frases sobre el estado de conservación del conjunto.
  caracteristicas_fisicas   soporte, técnica de escritura y estado, redactado para el
                            elemento 3.4.4 de la norma. Por ejemplo: documentos en papel de
                            la época, manuscritos en tinta ferrogálica y mecanografiados,
                            con acidez moderada y manchas de humedad en varios folios.
  alerta                    si el documento está ilegible, incompleto, o no corresponde al
                            asunto del inventario, dígalo aquí. Si todo está bien, vacío.

Reglas estrictas. No invente fechas, nombres de personas, entidades, lugares ni cifras que
no estén en el documento. En esta lectura no proponga todavía serie ni subserie: se eligen
después, contra la tabla de valoración del periodo que resulte de las fechas. Si una parte es ilegible, dígalo en observaciones en lugar de
suponer qué decía.

Responda EXCLUSIVAMENTE un objeto JSON con esta forma, sin texto adicional:

{{"nombre_del_expediente": "Informes de visitas técnicas",
"tramites": [{{"no_item": 1, "fecha": "1941-05-02",
"tipo_documental": "Informe de visita técnica N° 546-B al predio La Esperanza",
"no_radicado": "N/A",
"folio_desde": 1, "folio_hasta": 3, "observaciones": ""}}],
"asunto_del_documento": "", "coincide_con_el_inventario": "si", "por_que_no_coincide": "",
"fechas_del_documento": "", "folios_contados": 3,
"total_folios": 3, "estado_general": "", "caracteristicas_fisicas": "", "alerta": ""}}"""


CAMPOS_ELECCION = ("codigo_dependencia", "cod_serie", "cod_subserie", "subserie",
                   "porque", "seguridad")


def instruccion_eleccion_subserie(contexto: dict, opciones: list, tramites: list[dict]) -> str:
    """
    Segunda pasada, sin documento adjunto: con lo que ya se leyó, el modelo dice a qué
    subserie de la tabla de valoración del periodo pertenece el expediente.

    Va aparte de la lectura porque la subserie depende del periodo, y el periodo solo se
    conoce DESPUÉS de leer las fechas extremas del propio documento. Preguntarlo en la
    primera pasada obligaría a entregarle la tabla del periodo que dice el inventario, que
    es justamente el dato que no es de fiar.

    No lleva el documento adjunto: le basta lo que ya se leyó, y así la consulta es corta y
    barata. La lista que recibe es CERRADA: se le prohíbe expresamente devolver una serie o
    una subserie que no esté en ella, y de todos modos la respuesta se comprueba contra la
    tabla antes de guardarse.
    """
    # Cada renglón lleva su oficina productora: el mismo código de serie y de subserie se
    # repite entre las oficinas de un periodo y son clasificaciones distintas, porque el
    # productor es distinto. Sin ese dato el modelo no podría escoger entre dos renglones
    # que se ven iguales.
    lista = "\n".join(
        f"  {o.codigo_dependencia}|{o.cod_serie}|{o.cod_subserie}  ·  "
        f"{o.oficina_productora}  ·  {o.serie} › {o.subserie}" for o in opciones)
    leidos = "\n".join(
        f"  {t.get('no_item')}. {t.get('fecha') or 'SF'} · {t.get('tipo_documental') or 'sin tipo'}"
        for t in tramites) or "  (no se alcanzó a leer ningún trámite)"

    return f"""Usted es archivista de {contexto.get('fondo') or 'el fondo documental del proyecto'},
y está clasificando un expediente contra la Tabla de Valoración
Documental convalidada del periodo {contexto.get('periodo')}.

Expediente: {contexto.get('codigo_carpeta')}
Asunto que declara el inventario de origen (referencia, puede estar equivocado):
  {contexto.get('asunto') or 'no disponible'}
Asunto que se leyó del propio documento:
  {contexto.get('asunto_leido') or 'no disponible'}
Fechas extremas leídas: {contexto.get('fechas_extremas') or 'no disponibles'}

Trámites que se leyeron dentro del expediente:
{leidos}

Estas son TODAS las subseries de la tabla de valoración de este periodo. Es una lista
cerrada: usted tiene que escoger una de estas y no puede proponer ninguna otra, ni cambiarle
el nombre, ni juntar dos.

{lista}

Escoja aquella a la que pertenece el contenido que se leyó. Mande el contenido del
documento, no el asunto del inventario. Si duda entre dos, escoja la que abarque mejor el
grueso de los trámites y dígalo en el porqué.

Cuando dos renglones traigan los mismos códigos de serie y de subserie pero distinta oficina
productora, fíjese en quién produjo el documento: el membrete, la firma, la sección que lo
suscribe. Son clasificaciones distintas porque el productor es distinto.

Devuelva:
  codigo_dependencia  el código de dependencia de la línea escogida, el primero de los tres
                      números separados por barras. Es lo que dice de qué oficina es.
  cod_serie      el código de serie de la línea escogida, tal como está escrito arriba.
  cod_subserie   el código de subserie de esa misma línea, tal como está escrito arriba.
  subserie       el nombre de la subserie, copiado tal cual de la lista.
  porque         en una sola línea, qué del contenido leído la hace pertenecer ahí.
  seguridad      una de estas tres palabras exactas: alta, media, baja.

Responda EXCLUSIVAMENTE un objeto JSON con esas cinco claves, sin texto adicional:

{{"codigo_dependencia": "", "cod_serie": "", "cod_subserie": "", "subserie": "",
"porque": "", "seguridad": "alta"}}"""


