"""Redacción de la descripción ISAD(G) con modelos de lenguaje. Paquete aparte e independiente.

La descripción no forma parte del flujo de digitalización ni de la hoja de control: se usa cuando el
proyecto lo pide (típicamente en el Archivo Histórico). Recibe como DATOS lo que ya se verificó
(trámites, fechas, clasificación) y usa el reparto común de modelos (`arca.motor.lectores`); nunca
importa los módulos de la hoja de control. Si ningún modelo responde, devuelve None: jamás se fabrica
una descripción.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from arca.motor.lectores import Propuesta, _intentar

CAMPOS = ("titulo", "alcance_contenido", "organizacion", "notas")


def construir_instruccion(contexto: dict) -> str:
    """
    El modelo recibe hechos verificados, no adivina ninguno. La clasificación, el periodo y
    la valoración le llegan resueltos y su tarea es exclusivamente redactar.
    """
    tramites = "\n".join(
        f"  {t['no_item']}. {t.get('fecha') or 'sin fecha'} · {t.get('tipo_documental') or 'sin tipo'} "
        f"· folios {t.get('folio_desde')} a {t.get('folio_hasta')}"
        f"{' · ' + t['observaciones'] if t.get('observaciones') else ''}"
        for t in contexto.get("tramites", []))
    return f"""Usted es archivista y redacta la descripción de una unidad documental conforme a
la norma ISAD(G) segunda edición y a la norma técnica colombiana 4095 de 2013, para
{contexto.get('fondo') or 'el fondo documental del proyecto'}.

Datos ya verificados, que NO debe modificar ni contradecir:
  Código de carpeta: {contexto.get('codigo_carpeta')}
  Periodo institucional: {contexto.get('periodo')} ({contexto.get('rango_periodo')})
  Entidad productora: {contexto.get('entidad_productora')}
  Oficina productora: {contexto.get('oficina_productora')}
  Serie y subserie: {contexto.get('serie')} › {contexto.get('subserie')}
  Fechas extremas: {contexto.get('fechas_extremas')}
  Folios: {contexto.get('folios')}
  Asunto según el inventario de origen: {contexto.get('asunto_inventario')}

Trámites de la hoja de control:
{tramites or '  (sin trámites registrados)'}

Redacte únicamente estos cuatro elementos, en español, en prosa sobria de archivo, sin
viñetas, sin adjetivos de valoración y sin repetir información que ya esté en otros
elementos de la descripción:

  titulo             elemento 3.1.2, título atribuido. Una línea. Sin comillas.
  alcance_contenido  elemento 3.3.1. Qué contiene la unidad y de qué trata, en dos a cuatro
                     frases, apoyándose solo en los trámites listados.
  organizacion       elemento 3.3.4. Cómo está ordenada la unidad.
  notas              elemento 3.6.1. Solo si hay algo que advertir; si no, cadena vacía.

Reglas estrictas. No invente fechas, nombres de personas, lugares ni cifras que no aparezcan
arriba. No proponga serie ni subserie: ya están asignadas. Si la información es insuficiente
para un elemento, devuelva ese elemento como cadena vacía en lugar de suponer.

Responda EXCLUSIVAMENTE un objeto JSON con esas cuatro claves, sin texto adicional."""


def revisar_descripcion(db: Session, instruccion: str, redacto: str = "",
                        turno: int | None = None, modelo: str = "") -> Propuesta | None:
    """
    Cuarta tarea. Un modelo distinto mira lo que redactó el otro y dice qué le devolverían.

    Va sin documento adjunto: le basta lo que ya se describió y la lista de trámites que
    salió de la hoja de control. Por eso es barata y por eso el modelo local la puede asumir
    completa, salvo cuando fue él mismo quien redactó.

    NUNCA corrige ni aprueba. Devuelve hallazgos, que entran a la hoja de revisión marcados
    como lo que son: una opinión de máquina que una persona tiene que confirmar. El día que
    un agente apruebe lo de otro agente, se perdió el punto de control humano que sostiene
    el contrato.
    """
    from arca.motor.isadg.revisor import CAMPOS_REVISION

    # El que redactó no se revisa a sí mismo.
    fuera = tuple(x for x in (redacto,) if x)
    return _intentar(db, instruccion, None, 0, CAMPOS_REVISION, 700, turno,
                     sin_proveedor=fuera, modelo=modelo)


def describir(db: Session, contexto: dict, turno: int | None = None,
              modelo: str = "") -> Propuesta | None:
    """
    Pide la redacción al proveedor con más cuota. Si ese falla o se queda sin cuota, intenta
    con el otro. Si ninguno responde, devuelve None y el expediente queda esperando: jamás
    se fabrica una descripción.
    """
    return _intentar(db, construir_instruccion(contexto), None, contexto.get("folios"),
                     CAMPOS, 1500, turno, modelo=modelo)


def instruccion_descripcion(contexto: dict, tramites: list[dict]) -> str:
    """
    Instrucción para redactar los elementos narrativos de la descripción, a partir del mismo
    documento y de la hoja de control ya levantada y revisada.
    """
    listado = "\n".join(
        f"  {t.get('no_item')}. {t.get('fecha') or 'SF'} · {t.get('tipo_documental') or 'sin tipo'}"
        f" · folios {t.get('folio_desde')} a {t.get('folio_hasta')}"
        f"{' · ' + t['observaciones'] if t.get('observaciones') else ''}"
        for t in tramites)

    return f"""Usted es archivista y redacta la descripción de esta unidad documental conforme
a la norma ISAD(G) segunda edición y a la norma técnica colombiana 4095 de 2013, para
{contexto.get('fondo') or 'el fondo documental del proyecto'}.

Le adjunto el expediente digitalizado. Ya está levantada y revisada su hoja de control.

Datos ya verificados, que NO debe modificar ni contradecir:
  Código de carpeta: {contexto.get('codigo_carpeta')}
  Periodo institucional: {contexto.get('periodo')} ({contexto.get('rango_periodo')})
  Entidad productora: {contexto.get('entidad_productora')}
  Oficina productora: {contexto.get('oficina_productora')}
  Serie y subserie: {contexto.get('serie')} › {contexto.get('subserie')}
  Fechas extremas: {contexto.get('fechas_extremas')}
  Folios: {contexto.get('folios')}
  Asunto según el inventario: {contexto.get('asunto_inventario')}

Hoja de control del expediente:
{listado or '  (sin trámites registrados)'}

Redacte únicamente estos cuatro elementos, en español, en prosa sobria de archivo, sin
viñetas, sin adjetivos de valoración y sin repetir lo que ya dice otro elemento:

  titulo             elemento 3.1.2, título atribuido. Una sola línea, que diga de qué es el
                     expediente. Sin comillas y sin el código de carpeta.
  alcance_contenido  elemento 3.3.1. De qué trata la unidad y qué contiene, en dos a cuatro
                     frases, apoyándose en el documento y en los trámites listados. Mencione
                     los asuntos concretos, no generalidades.
  organizacion       elemento 3.3.4. Cómo está ordenada la unidad y cómo está foliada.
  notas              elemento 3.6.1. Solo lo que un investigador necesitaría saber y no cabe
                     en otro elemento, incluido lo que impida la consulta por estado de
                     conservación. Si no hay nada, deje la cadena vacía.

Reglas estrictas. No invente fechas, nombres, lugares ni cifras que no estén arriba o en el
documento. No proponga serie ni subserie: ya están asignadas. Si la información no alcanza
para un elemento, devuélvalo vacío en lugar de suponer.

Responda EXCLUSIVAMENTE un objeto JSON con esas cuatro claves, sin texto adicional."""
