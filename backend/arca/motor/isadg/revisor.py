"""
El cuarto papel: revisar lo descrito con la mirada de quien lo va a recibir.

La revisión de reglas —revision_isadg.py— atrapa lo que se puede comprobar sin criterio: el
elemento obligatorio vacío, el volumen sin soporte, la fecha que contradice la hoja de
control. Eso son hechos y se programan.

Lo que no se programa es si un título de verdad IDENTIFICA esa unidad y ninguna otra, si el
alcance dice algo que el título no dijera, y si lo descrito corresponde a los trámites que la
hoja de control registró. Ahí hace falta leer, y para leer hace falta un modelo.

TRES CONDICIONES, Y NINGUNA ES NEGOCIABLE.

Primera, el revisor es de un proveedor DISTINTO al que redactó. Es la regla de la casa
aplicada a las máquinas: nadie aprueba su propio trabajo. Un modelo que revisa su propia
redacción la encuentra excelente y la revisión no sirve de nada.

Segunda, el revisor SEÑALA y no corrige. No toca un solo campo de la descripción. Si
corrigiera, la descripción dejaría de ser la de la archivista y pasaría a ser la de una
cadena de modelos, y eso no se puede defender ante nadie.

Tercera, sus hallazgos entran con gravedad REVISE, nunca DEVUELVE. Un incumplimiento de norma
es un hecho; la opinión de un modelo sobre si un título está bien es una opinión. Se anota,
se marca como propuesta y la resuelve una persona con el expediente delante.
"""
from __future__ import annotations

from arca.motor.isadg.revision import REVISE, Hallazgo

CAMPOS_REVISION = ("titulo_identifica", "titulo_porque",
                   "alcance_aporta", "alcance_porque",
                   "corresponde_a_los_tramites", "tramites_porque",
                   "subserie_correcta", "subserie_porque", "subserie_sugerida")

_NO = ("no", "n", "falso", "incorrecto")
_DUDOSO = ("parcial", "dudoso", "quiza", "quizá", "tal vez", "revisar")


def instruccion(unidad: dict) -> str:
    """
    Lo que se le pide al revisor.

    Se le dan los datos y NO se le dan las conclusiones: no se le dice qué está mal ni se le
    insinúa. Y se le prohíbe reescribir, porque un modelo al que se le deja redactar termina
    redactando aunque se le haya pedido revisar.
    """
    tramites = unidad.get("tramites") or []
    listado = "\n".join(
        f"  {t.get('no_item')}. {t.get('fecha') or 's/f'} · {t.get('tipo_documental') or '?'} "
        f"· folios {t.get('folio_desde')}-{t.get('folio_hasta')}"
        + (f" · {t['observaciones']}" if t.get("observaciones") else "")
        for t in tramites[:40]) or "  (la hoja de control no registra trámites)"
    if len(tramites) > 40:
        listado += f"\n  … y {len(tramites) - 40} trámite(s) más."

    return f"""Usted revisa descripciones archivísticas para el Archivo General de la Nación de
Colombia. Aplica la NTC 4095:2013, que es la ISAD(G) colombiana. Su trabajo es decir qué le
devolverían a esta descripción, no mejorarla.

NO reescriba nada. NO proponga textos nuevos. Solo diga si cumple y por qué no.

UNIDAD DOCUMENTAL {unidad.get('codigo_referencia', '')}

Título atribuido (elemento 3.1.2):
  {unidad.get('titulo') or '(vacío)'}

Alcance y contenido (elemento 3.3.1):
  {unidad.get('alcance') or '(vacío)'}

Subserie en que quedó clasificada, según la tabla de valoración convalidada:
  {unidad.get('subserie') or '(sin subserie)'}

Fechas extremas: {unidad.get('fecha_inicial') or 's/f'} a {unidad.get('fecha_final') or 's/f'}
Volumen: {unidad.get('volumen') or '(vacío)'}

Trámites que la hoja de control registró para esta unidad:
{listado}

Revise tres cosas y responda con criterio archivístico, no de estilo.

1. EL TÍTULO. Un título atribuido tiene que identificar ESTA unidad y ninguna otra del fondo.
   Si sirve igual para doscientos expedientes, no sirve. Repetir el nombre de la subserie no
   es describir, es clasificar. Diga si identifica y, si no, qué información le falta:
   el asunto concreto, el lugar, la entidad de la que trata.

2. EL ALCANCE Y CONTENIDO. Ahí va lo que en el título no cabe: los tipos documentales que
   hay adentro, sobre qué versan y qué falta. Si solo reformula el título, no aporta. Diga
   si aporta y qué le falta.

3. LA CORRESPONDENCIA. Compare lo descrito con los trámites de arriba. Si el título dice
   «estudios de laboratorio» y los trámites son oficios remisorios, algo está mal. Diga si
   corresponde, y si la subserie en que quedó es la que le corresponde a lo que muestran los
   trámites. Si cree que no, diga cuál sería, pero solo si los trámites lo sustentan.

Responda EXCLUSIVAMENTE un objeto JSON con estas claves:
  "titulo_identifica": "si" o "no"
  "titulo_porque": una frase; vacía si identifica
  "alcance_aporta": "si" o "no"
  "alcance_porque": una frase; vacía si aporta
  "corresponde_a_los_tramites": "si", "no" o "parcial"
  "tramites_porque": una frase; vacía si corresponde
  "subserie_correcta": "si", "no" o "dudoso"
  "subserie_porque": una frase; vacía si está correcta
  "subserie_sugerida": el nombre de la subserie que usted propondría, o vacío
"""


def _frase(texto, por_omision: str) -> str:
    """Cierra la frase del modelo, que suele venir sin punto, para poder encadenarla."""
    t = str(texto or "").strip() or por_omision
    return t if t.endswith((".", "!", "?")) else t + "."


def _falla(valor: str) -> bool:
    v = str(valor or "").strip().lower()
    return v in _NO or v in _DUDOSO


def hallazgos_de(unidad: dict, campos: dict, proveedor: str = "") -> list[Hallazgo]:
    """
    Traduce lo que dijo el revisor a hallazgos, y los marca como lo que son.

    Todo sale con gravedad REVISE. La opinión de un modelo sobre un título no es un
    incumplimiento de norma y no puede bloquear una entrega: la mira una persona y decide.
    """
    codigo = unidad.get("codigo_referencia", "")
    firma = f" (lo señala el revisor {proveedor})" if proveedor else " (lo señala el revisor)"
    salida: list[Hallazgo] = []

    if _falla(campos.get("titulo_identifica")):
        salida.append(Hallazgo(
            REVISE, "3.1.2 Título · revisor", codigo, "Expediente",
            (campos.get("titulo_porque") or "El título no identifica la unidad.") + firma,
            "Confírmelo con el expediente delante. Si tiene razón, el título debe decir qué "
            "documento es, sobre qué asunto y de quién o sobre qué lugar."))

    if _falla(campos.get("alcance_aporta")):
        salida.append(Hallazgo(
            REVISE, "3.3.1 Alcance · revisor", codigo, "Expediente",
            (campos.get("alcance_porque") or "El alcance no agrega nada al título.") + firma,
            "Si tiene razón, agregue los tipos documentales, los asuntos y los vacíos que "
            "usted encontró al foliar."))

    if _falla(campos.get("corresponde_a_los_tramites")):
        salida.append(Hallazgo(
            REVISE, "3.3.1 contra la hoja de control · revisor", codigo, "Expediente",
            (campos.get("tramites_porque")
             or "Lo descrito no corresponde a los trámites registrados.") + firma,
            "Coteje la descripción con la hoja de control. Esta es la contradicción que la "
            "interventoría ve de una sola mirada."))

    if _falla(campos.get("subserie_correcta")):
        sugerida = (campos.get("subserie_sugerida") or "").strip()
        salida.append(Hallazgo(
            REVISE, "Clasificación · revisor", codigo, "Expediente",
            _frase(campos.get("subserie_porque"), "La subserie podría no ser la que corresponde.")
            + (f" Propone: {sugerida}." if sugerida else "") + firma,
            "Decídalo usted contra la tabla convalidada. La plataforma no reclasifica sola: "
            "cambiar una subserie mueve el código de referencia y la disposición final."))

    return salida


